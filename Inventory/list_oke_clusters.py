from pathlib import Path
from urllib.parse import urlsplit

import oci
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def endpoint_host(endpoint):
	if not endpoint:
		return ""
	parsed = urlsplit(endpoint if "://" in endpoint else f"//{endpoint}")
	return parsed.hostname or endpoint


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
	cluster_sheet = workbook.create_sheet("OKE Clusters")
	summary_sheet.append([
		"Region", "Cluster Count", "Public Endpoint Enabled", "Private-Only Endpoint"
	])
	cluster_sheet.append([
		"Region", "Compartment Name", "Cluster Name", "Cluster OCID", "Lifecycle State",
		"Kubernetes Version", "Endpoint Exposure", "Public Endpoint Enabled",
		"Public Endpoint IP", "Public Endpoint URL", "Private Endpoint IP",
		"Private Endpoint URL", "Kubernetes API Endpoint", "VCN Hostname Endpoint",
		"Endpoint Subnet OCID", "VCN OCID"
	])

	for region_subscription in regions:
		region_name = region_subscription.region_name
		print(f"Scanning region: {region_name}")
		region_config = dict(config, region=region_name)
		container_engine_client = oci.container_engine.ContainerEngineClient(region_config)
		cluster_count = 0
		public_endpoint_count = 0
		private_only_count = 0

		for compartment_id, compartment_name in compartment_names.items():
			clusters = oci.pagination.list_call_get_all_results(
				container_engine_client.list_clusters,
				compartment_id,
			).data

			for cluster in clusters:
				cluster_count += 1
				endpoint_config = cluster.endpoint_config
				endpoints = cluster.endpoints
				public_enabled = endpoint_config.is_public_ip_enabled if endpoint_config else None
				public_endpoint = endpoints.public_endpoint if endpoints else ""
				private_endpoint = endpoints.private_endpoint if endpoints else ""
				public_enabled_value = (
					"Yes" if public_enabled is True
					else "No" if public_enabled is False
					else "Unknown"
				)
				if public_enabled is True:
					public_endpoint_count += 1
				if public_enabled is False and private_endpoint:
					private_only_count += 1

				if public_enabled is True and private_endpoint:
					exposure = "Public and private"
				elif public_enabled is True:
					exposure = "Public endpoint enabled"
				elif private_endpoint:
					exposure = "Private only"
				else:
					exposure = "Endpoint unavailable"

				cluster_sheet.append([
					region_name,
					compartment_name,
					cluster.name,
					cluster.id,
					cluster.lifecycle_state,
					cluster.kubernetes_version,
					exposure,
					public_enabled_value,
					endpoint_host(public_endpoint),
					public_endpoint,
					endpoint_host(private_endpoint),
					private_endpoint,
					endpoints.kubernetes if endpoints else "",
					endpoints.vcn_hostname_endpoint if endpoints else "",
					endpoint_config.subnet_id if endpoint_config else "",
					cluster.vcn_id,
				])

		summary_sheet.append([
			region_name, cluster_count, public_endpoint_count, private_only_count
		])
		print(
			f"  Found {cluster_count} clusters; {public_endpoint_count} with public endpoints, "
			f"{private_only_count} private-only"
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

	output_path = Path(__file__).with_name("OKE_Cluster_Endpoint_Inventory.xlsx")
	workbook.save(output_path)
	print(f"Inventory written to {output_path}")


if __name__ == "__main__":
	main()
