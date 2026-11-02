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
		lifecycle_state="ACTIVE",
	).data
	compartment_names = {compartment.id: compartment.name for compartment in compartments}
	compartment_names.setdefault(tenancy_id, "root")
	regions = identity_client.list_region_subscriptions(tenancy_id).data

	workbook = Workbook()
	summary_sheet = workbook.active
	summary_sheet.title = "Summary"
	vcn_sheet = workbook.create_sheet("VCNs")
	subnet_sheet = workbook.create_sheet("Subnets")

	summary_sheet.append(["Region", "VCN Count", "Subnet Count", "Public Subnets", "Private Subnets"])
	vcn_sheet.append([
		"Region", "Compartment Name", "VCN Name", "VCN ID", "IPv4 CIDR Ranges",
		"IPv6 CIDR Ranges", "Lifecycle State", "Created", "Subnet Count"
	])
	subnet_sheet.append([
		"Region", "Compartment Name", "VCN Name", "VCN ID", "VCN IPv4 CIDR Ranges",
		"Subnet Name", "Subnet ID", "Subnet IPv4 CIDR Range", "Subnet IPv6 CIDR Ranges",
		"Subnet Type", "Public IP Prohibited", "Availability Domain", "Lifecycle State", "Created"
	])

	for region_subscription in regions:
		region_name = region_subscription.region_name
		print(f"Scanning region: {region_name}")
		region_config = dict(config, region=region_name)
		network_client = oci.core.VirtualNetworkClient(region_config)
		region_vcns = 0
		region_subnets = 0
		region_public_subnets = 0
		region_private_subnets = 0

		for compartment_id, compartment_name in compartment_names.items():
			print(f"Checking compartment: {compartment_name}")
			vcns = oci.pagination.list_call_get_all_results(
				network_client.list_vcns,
				compartment_id,
			).data
			subnets = oci.pagination.list_call_get_all_results(
				network_client.list_subnets,
				compartment_id,
			).data
			vcns_by_id = {vcn.id: vcn for vcn in vcns}
			subnet_counts = {}

			for subnet in subnets:
				subnet_counts[subnet.vcn_id] = subnet_counts.get(subnet.vcn_id, 0) + 1
				vcn = vcns_by_id.get(subnet.vcn_id)
				is_private = bool(subnet.prohibit_public_ip_on_vnic)
				if is_private:
					region_private_subnets += 1
				else:
					region_public_subnets += 1
				subnet_cidrs = subnet.ipv4_cidr_blocks or ([subnet.cidr_block] if subnet.cidr_block else [])
				vcn_cidrs = (vcn.cidr_blocks or ([vcn.cidr_block] if vcn.cidr_block else [])) if vcn else []
				subnet_sheet.append([
					region_name,
					compartment_name,
					vcn.display_name if vcn else "VCN not found",
					subnet.vcn_id,
					join_values(vcn_cidrs),
					subnet.display_name,
					subnet.id,
					join_values(subnet_cidrs),
					join_values(subnet.ipv6_cidr_blocks or ([subnet.ipv6_cidr_block] if subnet.ipv6_cidr_block else [])),
					"Private" if is_private else "Public",
					"Yes" if is_private else "No",
					subnet.availability_domain or "Regional",
					subnet.lifecycle_state,
					subnet.time_created.isoformat() if subnet.time_created else "",
				])

			for vcn in vcns:
				region_vcns += 1
				vcn_sheet.append([
					region_name,
					compartment_name,
					vcn.display_name,
					vcn.id,
					join_values(vcn.cidr_blocks or ([vcn.cidr_block] if vcn.cidr_block else [])),
					join_values(vcn.ipv6_cidr_blocks),
					vcn.lifecycle_state,
					vcn.time_created.isoformat() if vcn.time_created else "",
					subnet_counts.get(vcn.id, 0),
				])

			region_subnets += len(subnets)

		summary_sheet.append([
			region_name,
			region_vcns,
			region_subnets,
			region_public_subnets,
			region_private_subnets,
		])
		print(
			f"  Found {region_vcns} VCNs and {region_subnets} subnets "
			f"({region_public_subnets} public, {region_private_subnets} private)"
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

	output_path = Path(__file__).with_name("VCN_Subnet_Inventory.xlsx")
	workbook.save(output_path)
	print(f"Inventory written to {output_path}")


if __name__ == "__main__":
	main()
