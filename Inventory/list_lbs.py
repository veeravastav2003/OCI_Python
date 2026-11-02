from pathlib import Path

import oci
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def join_values(values):
	return "; ".join(str(value) for value in (values or []) if value)


def main():
	config = oci.config.from_file()
	tenancy_id = config["tenancy"]
	identity_client = oci.identity.IdentityClient(config)
	compartments = oci.pagination.list_call_get_all_results(
		identity_client.list_compartments,
		compartment_id=tenancy_id,
		compartment_id_in_subtree=True,
		access_level="ANY",
		lifecycle_state="ACTIVE",
	).data
	compartment_names = {compartment.id: compartment.name for compartment in compartments}
	compartment_names.setdefault(tenancy_id, "root")
	# OCI returns region subscriptions as a complete, non-paginated list.
	regions = identity_client.list_region_subscriptions(tenancy_id).data

	workbook = Workbook()
	summary_sheet = workbook.active
	summary_sheet.title = "Summary"
	load_balancer_sheet = workbook.create_sheet("Load Balancers")

	summary_sheet.append([
		"Region", "Load Balancer Count", "Public Load Balancers", "Private Load Balancers",
		"Private LBs on Subnets Allowing Public IPs"
	])
	load_balancer_sheet.append([
		"Region", "Compartment Name", "Load Balancer Name", "Load Balancer OCID",
		"Private IP Addresses", "Public IP Addresses", "LB Visibility", "Subnet Names",
		"Subnet CIDRs", "Subnet Public-IP Setting(s)", "Subnet OCIDs", "Lifecycle State",
		"Lookup Status"
	])

	for region_subscription in regions:
		region_name = region_subscription.region_name
		print(f"Scanning region: {region_name}")
		region_config = dict(config, region=region_name)
		lb_client = oci.load_balancer.LoadBalancerClient(region_config)
		network_client = oci.core.VirtualNetworkClient(region_config)
		subnet_cache = {}
		region_lb_count = 0
		region_public_count = 0
		region_private_count = 0
		region_private_on_public_ip_subnet_count = 0

		for compartment_id, compartment_name in compartment_names.items():
			load_balancers = oci.pagination.list_call_get_all_results(
				lb_client.list_load_balancers,
				compartment_id,
				detail="full",
			).data

			for load_balancer in load_balancers:
				region_lb_count += 1
				is_private = bool(load_balancer.is_private)
				if is_private:
					region_private_count += 1
				else:
					region_public_count += 1

				private_ips = []
				public_ips = []
				for address in load_balancer.ip_addresses or []:
					if address.is_public:
						if address.ip_address:
							public_ips.append(address.ip_address)
					elif address.ip_address:
						private_ips.append(address.ip_address)

				subnet_names = []
				subnet_cidrs = []
				subnet_ip_settings = []
				lookup_issues = []
				subnet_ids = load_balancer.subnet_ids or []
				for subnet_id in subnet_ids:
					if subnet_id not in subnet_cache:
						try:
							subnet = network_client.get_subnet(subnet_id).data
							subnet_cache[subnet_id] = (
								subnet.display_name,
								subnet.cidr_block,
								not bool(subnet.prohibit_public_ip_on_vnic),
								"",
							)
						except oci.exceptions.ServiceError as exc:
							subnet_cache[subnet_id] = (
								"", "", None,
								f"Subnet lookup failed ({exc.status}): {exc.message}"
							)
					subnet_name, subnet_cidr, public_ip_allowed, subnet_error = subnet_cache[subnet_id]
					if subnet_name:
						subnet_names.append(subnet_name)
					if subnet_cidr:
						subnet_cidrs.append(subnet_cidr)
					if public_ip_allowed is not None:
						subnet_ip_settings.append(
							"Public IP allowed" if public_ip_allowed else "Public IP prohibited"
						)
					if subnet_error:
						lookup_issues.append(subnet_error)

				if is_private and any(
					setting is True
					for _, _, setting, error in (subnet_cache[subnet_id] for subnet_id in subnet_ids)
					if not error
				):
					region_private_on_public_ip_subnet_count += 1

				load_balancer_sheet.append([
					region_name,
					compartment_name,
					load_balancer.display_name,
					load_balancer.id,
					join_values(private_ips),
					join_values(public_ips),
					"Private" if is_private else "Public",
					join_values(subnet_names),
					join_values(subnet_cidrs),
					join_values(subnet_ip_settings),
					join_values(subnet_ids),
					load_balancer.lifecycle_state,
					"; ".join(lookup_issues) or "OK",
				])

		summary_sheet.append([
			region_name,
			region_lb_count,
			region_public_count,
			region_private_count,
			region_private_on_public_ip_subnet_count,
		])
		print(
			f"  Found {region_lb_count} load balancers "
			f"({region_public_count} public, {region_private_count} private); "
			f"{region_private_on_public_ip_subnet_count} private LBs use subnets allowing public IPs"
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

	output_path = Path(__file__).with_name("Load_Balancer_Inventory.xlsx")
	workbook.save(output_path)
	print(f"Inventory written to {output_path}")


if __name__ == "__main__":
	main()
