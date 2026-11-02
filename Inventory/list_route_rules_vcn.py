from pathlib import Path

import oci
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


TARGET_TYPES = {
	"internetgateway": "Internet Gateway",
	"natgateway": "NAT Gateway",
	"servicegateway": "Service Gateway",
	"drg": "Dynamic Routing Gateway",
	"privateip": "Private IP",
	"localpeeringgateway": "Local Peering Gateway",
	"networkfirewall": "Network Firewall",
}


def join_values(values):
	return "; ".join(str(value) for value in (values or []) if value)


def target_type(target_id, gateways_by_id):
	if target_id in gateways_by_id:
		return "Internet Gateway"
	if not target_id:
		return "Unknown"
	resource_type = target_id.split(".")[1] if len(target_id.split(".")) > 1 else "unknown"
	return TARGET_TYPES.get(resource_type.lower(), resource_type)


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
	regions = identity_client.list_region_subscriptions(tenancy_id).data

	workbook = Workbook()
	summary_sheet = workbook.active
	summary_sheet.title = "Summary"
	vcn_sheet = workbook.create_sheet("VCNs")
	subnet_sheet = workbook.create_sheet("Subnets")
	route_rule_sheet = workbook.create_sheet("Route Rules")

	summary_sheet.append([
		"Region", "VCN Count", "Subnet Count", "Route Table Count",
		"Route Rule Count", "VCNs With Internet Gateway", "Enabled Internet Gateways"
	])
	vcn_sheet.append([
		"Region", "Compartment Name", "VCN Name", "VCN OCID", "IPv4 CIDR Ranges",
		"Lifecycle State", "Default Route Table Name", "Default Route Table OCID",
		"Internet Gateway Attached", "Internet Gateway Names", "Internet Gateway OCIDs",
		"Internet Gateway Enabled States", "Internet Gateway Lifecycle States"
	])
	subnet_sheet.append([
		"Region", "Compartment Name", "VCN Name", "VCN OCID", "Subnet Name",
		"Subnet OCID", "Subnet CIDR", "Subnet Public-IP Setting", "Lifecycle State",
		"Route Table Name", "Route Table OCID", "Route Table Source", "Route Rule Count",
		"Internet Gateway Attached", "Internet Gateway Names"
	])
	route_rule_sheet.append([
		"Region", "Compartment Name", "VCN Name", "VCN OCID", "Route Table Name",
		"Route Table OCID", "Associated Subnet Names", "Rule Destination",
		"Destination Type", "Route Type", "Target Type", "Target Name", "Target OCID",
		"Target Is Internet Gateway", "Internet Gateway Enabled", "Rule Description"
	])

	for region_subscription in regions:
		region_name = region_subscription.region_name
		print(f"Scanning region: {region_name}")
		region_config = dict(config, region=region_name)
		network_client = oci.core.VirtualNetworkClient(region_config)

		vcns_by_id = {}
		route_tables_by_id = {}
		gateways_by_id = {}
		gateways_by_vcn = {}
		subnet_records = []
		subnets_by_route_table = {}
		region_subnet_count = 0
		region_route_rule_count = 0
		region_enabled_gateway_count = 0

		for compartment_id, compartment_name in compartment_names.items():
			vcns = oci.pagination.list_call_get_all_results(
				network_client.list_vcns,
				compartment_id,
			).data
			route_tables = oci.pagination.list_call_get_all_results(
				network_client.list_route_tables,
				compartment_id,
			).data
			gateways = oci.pagination.list_call_get_all_results(
				network_client.list_internet_gateways,
				compartment_id,
			).data
			subnets = oci.pagination.list_call_get_all_results(
				network_client.list_subnets,
				compartment_id,
			).data

			for vcn in vcns:
				vcns_by_id[vcn.id] = {
					"resource": vcn,
					"compartment_name": compartment_name,
				}
			for route_table in route_tables:
				route_tables_by_id[route_table.id] = route_table
			for gateway in gateways:
				gateways_by_id[gateway.id] = gateway
				gateways_by_vcn.setdefault(gateway.vcn_id, []).append(gateway)
				if gateway.is_enabled:
					region_enabled_gateway_count += 1

			for subnet in subnets:
				vcn_info = vcns_by_id.get(subnet.vcn_id)
				vcn = vcn_info["resource"] if vcn_info else None
				route_table_id = subnet.route_table_id or (
					vcn.default_route_table_id if vcn else None
				)
				route_table = route_tables_by_id.get(route_table_id)
				subnet_info = {
					"resource": subnet,
					"compartment_name": compartment_name,
					"vcn": vcn,
					"vcn_compartment_name": vcn_info["compartment_name"] if vcn_info else compartment_name,
					"route_table_id": route_table_id,
				}
				subnet_records.append(subnet_info)
				if route_table_id:
					subnets_by_route_table.setdefault(route_table_id, []).append(subnet.display_name)
				region_subnet_count += 1

		for vcn_id, vcn_info in vcns_by_id.items():
			vcn = vcn_info["resource"]
			gateways = gateways_by_vcn.get(vcn_id, [])
			default_route_table = route_tables_by_id.get(vcn.default_route_table_id)
			vcn_sheet.append([
				region_name,
				vcn_info["compartment_name"],
				vcn.display_name,
				vcn.id,
				join_values(vcn.cidr_blocks or ([vcn.cidr_block] if vcn.cidr_block else [])),
				vcn.lifecycle_state,
				default_route_table.display_name if default_route_table else "",
				vcn.default_route_table_id,
				"Yes" if gateways else "No",
				join_values(gateway.display_name for gateway in gateways),
				join_values(gateway.id for gateway in gateways),
				join_values("Enabled" if gateway.is_enabled else "Disabled" for gateway in gateways),
				join_values(gateway.lifecycle_state for gateway in gateways),
			])

		for subnet_info in subnet_records:
			subnet = subnet_info["resource"]
			vcn = subnet_info["vcn"]
			route_table_id = subnet_info["route_table_id"]
			route_table = route_tables_by_id.get(route_table_id)
			gateways = gateways_by_vcn.get(subnet.vcn_id, [])
			subnet_type = (
				"Public IP prohibited" if subnet.prohibit_public_ip_on_vnic
				else "Public IP allowed"
			)
			subnet_sheet.append([
				region_name,
				subnet_info["compartment_name"],
				vcn.display_name if vcn else "VCN not found",
				subnet.vcn_id,
				subnet.display_name,
				subnet.id,
				join_values(subnet.ipv4_cidr_blocks or ([subnet.cidr_block] if subnet.cidr_block else [])),
				subnet_type,
				subnet.lifecycle_state,
				route_table.display_name if route_table else "Route table not found",
				route_table_id,
				"Subnet override" if subnet.route_table_id else "VCN default",
				len(route_table.route_rules or []) if route_table else 0,
				"Yes" if gateways else "No",
				join_values(gateway.display_name for gateway in gateways),
			])

		for route_table_id, route_table in route_tables_by_id.items():
			vcn_info = vcns_by_id.get(route_table.vcn_id)
			vcn = vcn_info["resource"] if vcn_info else None
			compartment_name = vcn_info["compartment_name"] if vcn_info else compartment_names.get(route_table.compartment_id, "")
			associated_subnets = join_values(subnets_by_route_table.get(route_table_id, []))
			route_rules = route_table.route_rules or []
			if not route_rules:
				route_rule_sheet.append([
					region_name, compartment_name, vcn.display_name if vcn else "VCN not found",
					route_table.vcn_id, route_table.display_name, route_table.id,
					associated_subnets, "", "", "", "", "", "", "No", "", "No route rules",
				])
				continue

			for rule in route_rules:
				target_id = rule.network_entity_id or ""
				gateway = gateways_by_id.get(target_id)
				target_name = gateway.display_name if gateway else ""
				route_rule_sheet.append([
					region_name,
					compartment_name,
					vcn.display_name if vcn else "VCN not found",
					route_table.vcn_id,
					route_table.display_name,
					route_table.id,
					associated_subnets,
					rule.destination or rule.cidr_block or "",
					rule.destination_type or "",
					rule.route_type or "",
					target_type(target_id, gateways_by_id),
					target_name,
					target_id,
					"Yes" if gateway else "No",
					"Enabled" if gateway and gateway.is_enabled else (
						"Disabled" if gateway else ""
					),
					rule.description or "",
				])

		region_route_table_count = len(route_tables_by_id)
		region_vcn_count = len(vcns_by_id)
		region_route_rule_count = sum(
			len(route_table.route_rules or [])
			for route_table in route_tables_by_id.values()
		)
		summary_sheet.append([
			region_name,
			region_vcn_count,
			region_subnet_count,
			region_route_table_count,
			region_route_rule_count,
			sum(bool(gateways_by_vcn.get(vcn_id)) for vcn_id in vcns_by_id),
			region_enabled_gateway_count,
		])
		print(
			f"  Found {region_vcn_count} VCNs, {region_subnet_count} subnets, "
			f"{region_route_table_count} route tables, {region_route_rule_count} route rules across those tables"
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

	output_path = Path(__file__).with_name("VCN_Route_Rule_Inventory.xlsx")
	workbook.save(output_path)
	print(f"Inventory written to {output_path}")


if __name__ == "__main__":
	main()
