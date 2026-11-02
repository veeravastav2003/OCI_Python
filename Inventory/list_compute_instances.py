from pathlib import Path

import oci
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def as_text(value):
	return value.isoformat() if hasattr(value, "isoformat") else value


def format_values(values):
	return "; ".join(str(value) for value in values if value)


def fetch_vnic_private_ips(network_client, vnic_id):
	return oci.pagination.list_call_get_all_results(
		network_client.list_private_ips,
		vnic_id=vnic_id,
	).data


def collect_vnic_ip_details(network_client, vnic, private_ips, public_ip_cache):
	if not private_ips:
		primary_private_ip = vnic.private_ip or ""
		public_ip = vnic.public_ip or ""
		ip_rows = [{
			"ip_type": "Primary",
			"private_ip": primary_private_ip,
			"public_ip": public_ip,
			"ip_state": "",
			"lookup_status": "VNIC fallback",
		}]
		return primary_private_ip, [], ([public_ip] if public_ip else []), ip_rows, []

	primary_private_ip = next(
		(ip.ip_address for ip in private_ips if ip.is_primary),
		vnic.private_ip or "",
	)
	secondary_private_ips = [
		ip.ip_address for ip in private_ips
		if not ip.is_primary and ip.ip_address
	]
	public_ip_addresses = []
	ip_rows = []
	lookup_issues = []

	for private_ip in private_ips:
		if private_ip.id not in public_ip_cache:
			try:
				public_ip_cache[private_ip.id] = (
					network_client.get_public_ip_by_private_ip_id(
						get_public_ip_by_private_ip_id_details=(
							oci.core.models.GetPublicIpByPrivateIpIdDetails(
								private_ip_id=private_ip.id
							)
						)
					).data.ip_address,
					"OK",
				)
			except oci.exceptions.ServiceError as exc:
				status = "No public IP assigned" if exc.status == 404 else (
					f"Public IP lookup failed ({exc.status}): {exc.message}"
				)
				public_ip_cache[private_ip.id] = ("", status)

		public_ip, public_ip_status = public_ip_cache[private_ip.id]
		if public_ip:
			public_ip_addresses.append(public_ip)
		if public_ip_status.startswith("Public IP lookup failed"):
			lookup_issues.append(public_ip_status)
		ip_rows.append({
			"ip_type": "Primary" if private_ip.is_primary else "Secondary",
			"private_ip": private_ip.ip_address or "",
			"public_ip": public_ip,
			"ip_state": private_ip.ip_state or "",
			"lookup_status": public_ip_status,
		})

	if vnic.public_ip and vnic.public_ip not in public_ip_addresses:
		public_ip_addresses.append(vnic.public_ip)

	return (
		primary_private_ip,
		secondary_private_ips,
		public_ip_addresses,
		ip_rows,
		lookup_issues,
	)


def main():
	config = oci.config.from_file()
	tenancy_id = config["tenancy"]
	identity_client = oci.identity.IdentityClient(config)
	compartments = oci.pagination.list_call_get_all_results(
		identity_client.list_compartments,
		compartment_id=tenancy_id,
		compartment_id_in_subtree=True,
	).data
	compartment_names = {compartment.id: compartment.name for compartment in compartments}
	compartment_names.setdefault(tenancy_id, "root")
	regions = identity_client.list_region_subscriptions(tenancy_id).data

	workbook = Workbook()
	summary_sheet = workbook.active
	summary_sheet.title = "Summary"
	instances_sheet = workbook.create_sheet("Instances")
	vnic_sheet = workbook.create_sheet("VNIC Details")
	vnic_ips_sheet = workbook.create_sheet("VNIC IPs")

	summary_sheet.append([
		"Region", "Total Instances", "Running Instances", "Instances Without Attached VNIC"
	])
	instances_sheet.append([
		"Region", "Compartment Name", "Instance Name", "Instance ID", "Lifecycle State",
		"Shape", "Availability Domain", "Created", "VNIC Count", "VNIC Names",
		"Primary Private IP Addresses", "Secondary Private IP Addresses",
		"Public IP Addresses", "IPv6 Addresses", "Subnet Names", "Subnet IDs"
	])
	vnic_sheet.append([
		"Region", "Compartment Name", "Instance Name", "Instance ID", "Instance State",
		"VNIC Attachment ID", "VNIC ID", "VNIC Name", "Primary VNIC", "VNIC State",
		"Primary Private IP", "Secondary Private IPs", "Public IP Addresses", "IPv6 Addresses",
		"Subnet Name", "Subnet ID", "Subnet CIDR", "Lookup Status"
	])
	vnic_ips_sheet.append([
		"Region", "Compartment Name", "Instance Name", "Instance ID", "VNIC Name",
		"VNIC ID", "IP Type", "Private IP", "Associated Public IP", "IP State",
		"Lookup Status"
	])

	for region_subscription in regions:
		region_name = region_subscription.region_name
		print(f"Scanning region: {region_name}")
		region_config = dict(config, region=region_name)
		compute_client = oci.core.ComputeClient(region_config)
		network_client = oci.core.VirtualNetworkClient(region_config)
		subnet_cache = {}
		private_ip_cache = {}
		public_ip_cache = {}
		total_instances = 0
		running_instances = 0
		instances_without_vnic = 0

		for compartment_id, compartment_name in compartment_names.items():
			print(f"Checking compartment: {compartment_name}")
			instances = oci.pagination.list_call_get_all_results(
				compute_client.list_instances,
				compartment_id,
			).data
			attachments = oci.pagination.list_call_get_all_results(
				compute_client.list_vnic_attachments,
				compartment_id,
			).data
			attachments_by_instance = {}
			for attachment in attachments:
				if attachment.lifecycle_state == "ATTACHED" and attachment.vnic_id:
					attachments_by_instance.setdefault(attachment.instance_id, []).append(attachment)

			for instance in instances:
				total_instances += 1
				if instance.lifecycle_state == "RUNNING":
					running_instances += 1

				vnic_rows = []
				attached_attachments = attachments_by_instance.get(instance.id, [])

				for attachment in attached_attachments:
					try:
						vnic = network_client.get_vnic(attachment.vnic_id).data
					except oci.exceptions.ServiceError as exc:
						vnic_sheet.append([
							region_name, compartment_name, instance.display_name, instance.id,
							instance.lifecycle_state, attachment.id, attachment.vnic_id,
							"", "Yes" if attachment.nic_index == 0 else "No", "Unavailable",
							"", "", "", "", "", attachment.subnet_id or "", "",
							f"VNIC lookup failed ({exc.status}): {exc.message}"
						])
						continue

					lookup_issues = []
					if vnic.id not in private_ip_cache:
						try:
							private_ip_cache[vnic.id] = fetch_vnic_private_ips(
								network_client, vnic.id
							)
						except oci.exceptions.ServiceError as exc:
							private_ip_cache[vnic.id] = None
							lookup_issues.append(
								f"Private IP lookup failed ({exc.status}): {exc.message}"
							)
					private_ips = private_ip_cache[vnic.id]
					if private_ips is None:
						lookup_issues.append("Private IP list unavailable; using VNIC primary IP")
					(
						primary_private_ip,
						secondary_private_ips,
						public_ip_addresses,
						vnic_ip_rows,
						public_ip_issues,
					) = collect_vnic_ip_details(
						network_client,
						vnic,
						private_ips,
						public_ip_cache,
					)
					lookup_issues.extend(public_ip_issues)
					for ip_row in vnic_ip_rows:
						vnic_ips_sheet.append([
							region_name, compartment_name, instance.display_name, instance.id,
							vnic.display_name, vnic.id, ip_row["ip_type"], ip_row["private_ip"],
							ip_row["public_ip"], ip_row["ip_state"], ip_row["lookup_status"],
						])

					subnet_id = vnic.subnet_id or attachment.subnet_id
					subnet_name = ""
					subnet_cidr = ""
					if subnet_id:
						if subnet_id not in subnet_cache:
							try:
								subnet = network_client.get_subnet(subnet_id).data
								subnet_cache[subnet_id] = (subnet.display_name, subnet.cidr_block)
							except oci.exceptions.ServiceError as exc:
								subnet_cache[subnet_id] = (
									f"Subnet lookup failed ({exc.status}): {exc.message}", ""
								)
						subnet_name, subnet_cidr = subnet_cache[subnet_id]
						if subnet_name.startswith("Subnet lookup failed"):
							lookup_issues.append(subnet_name)
							subnet_name = ""

					ipv6_addresses = vnic.ipv6_addresses or []
					vnic_rows.append({
						"attachment_id": attachment.id,
						"vnic_id": vnic.id,
						"vnic_name": vnic.display_name,
						"is_primary": attachment.nic_index == 0 or bool(vnic.is_primary),
						"vnic_state": vnic.lifecycle_state,
						"primary_private_ip": primary_private_ip,
						"secondary_private_ips": secondary_private_ips,
						"public_ip_addresses": public_ip_addresses,
						"ipv6_addresses": ipv6_addresses,
						"subnet_name": subnet_name,
						"subnet_id": subnet_id,
						"subnet_cidr": subnet_cidr,
						"lookup_status": "; ".join(lookup_issues) or "OK",
					})
					vnic_sheet.append([
						region_name, compartment_name, instance.display_name, instance.id,
						instance.lifecycle_state, attachment.id, vnic.id, vnic.display_name,
						"Yes" if attachment.nic_index == 0 or vnic.is_primary else "No",
						vnic.lifecycle_state, primary_private_ip,
						format_values(secondary_private_ips), format_values(public_ip_addresses),
						format_values(ipv6_addresses), subnet_name, subnet_id, subnet_cidr,
						"; ".join(lookup_issues) or "OK"
					])

				if not attached_attachments:
					instances_without_vnic += 1

				instances_sheet.append([
					region_name, compartment_name, instance.display_name, instance.id,
					instance.lifecycle_state, instance.shape, instance.availability_domain,
					as_text(instance.time_created), len(attached_attachments),
					format_values(row["vnic_name"] for row in vnic_rows),
					format_values(row["primary_private_ip"] for row in vnic_rows),
					format_values(address for row in vnic_rows for address in row["secondary_private_ips"]),
					format_values(address for row in vnic_rows for address in row["public_ip_addresses"]),
					format_values(address for row in vnic_rows for address in row["ipv6_addresses"]),
					format_values(row["subnet_name"] for row in vnic_rows),
					format_values(row["subnet_id"] for row in vnic_rows),
				])

		summary_sheet.append([
			region_name, total_instances, running_instances, instances_without_vnic
		])
		print(
			f"  Found {total_instances} instances; "
			f"{running_instances} running; {instances_without_vnic} without attached VNICs"
		)

	for sheet in workbook.worksheets:
		sheet.freeze_panes = "A2"
		sheet.auto_filter.ref = sheet.dimensions
		for cell in sheet[1]:
			cell.font = Font(bold=True, color="FFFFFF")
			cell.fill = PatternFill("solid", fgColor="245B63")
		for column_cells in sheet.columns:
			width = min(
				max(max(len(str(cell.value or "")) for cell in column_cells) + 2, 12),
				52,
			)
			sheet.column_dimensions[get_column_letter(column_cells[0].column)].width = width

	output_path = Path(__file__).with_name("Compute_Instances_Inventory.xlsx")
	workbook.save(output_path)
	print(f"Inventory written to {output_path}")


if __name__ == "__main__":
	main()
