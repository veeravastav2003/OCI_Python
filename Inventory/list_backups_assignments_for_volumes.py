from pathlib import Path

import oci
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def as_text(value):
	return value.isoformat() if value else ""


def resolve_volume_backup_policy(block_storage_client, asset_id, policy_cache):
	try:
		assignments = oci.pagination.list_call_get_all_results(
			block_storage_client.get_volume_backup_policy_asset_assignment,
			asset_id=asset_id,
		).data
	except oci.exceptions.ServiceError as exc:
		if exc.status == 404:
			return "No", "", "", "No backup policy assigned"
		return "Unknown", "", "", f"Assignment lookup failed ({exc.status}): {exc.message}"

	if not assignments:
		return "No", "", "", "No backup policy assigned"

	policy_id = assignments[0].policy_id
	if policy_id not in policy_cache:
		try:
			policy = block_storage_client.get_volume_backup_policy(policy_id).data
			policy_cache[policy_id] = (policy.display_name, "")
		except oci.exceptions.ServiceError as exc:
			policy_cache[policy_id] = (
				"",
				f"Backup policy lookup failed ({exc.status}): {exc.message}",
			)

	policy_name, lookup_error = policy_cache[policy_id]
	return "Yes", policy_name, policy_id, lookup_error or "OK"


def resolve_filesystem_snapshot_policy(file_storage_client, policy_id, policy_cache):
	if not policy_id:
		return "No", "", "", "No snapshot policy attached"

	if policy_id not in policy_cache:
		try:
			policy = file_storage_client.get_filesystem_snapshot_policy(policy_id).data
			policy_cache[policy_id] = (policy.display_name, policy.lifecycle_state, "")
		except oci.exceptions.ServiceError as exc:
			policy_cache[policy_id] = (
				"",
				"",
				f"Snapshot policy lookup failed ({exc.status}): {exc.message}",
			)

	policy_name, policy_state, lookup_error = policy_cache[policy_id]
	return "Yes", policy_name, policy_state, lookup_error or "OK"


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
	boot_volume_sheet = workbook.create_sheet("Boot Volumes")
	block_volume_sheet = workbook.create_sheet("Block Volumes")
	filesystem_sheet = workbook.create_sheet("File Systems")

	summary_sheet.append([
		"Region", "Boot Volumes", "Boot Volumes With Backup Policy",
		"Block Volumes", "Block Volumes With Backup Policy",
		"File Systems", "File Systems With Snapshot Policy",
	])
	volume_headers = [
		"Region", "Compartment Name", "Availability Domain", "Volume Name", "Volume OCID",
		"Lifecycle State", "Size (GB)", "Backup Policy Attached", "Backup Policy Name",
		"Backup Policy OCID", "Policy Lookup Status",
	]
	boot_volume_sheet.append(volume_headers)
	block_volume_sheet.append(volume_headers)
	filesystem_sheet.append([
		"Region", "Compartment Name", "Availability Domain", "File System Name",
		"File System OCID", "Lifecycle State", "Metered Bytes", "Snapshot Policy Attached",
		"Snapshot Policy Name", "Snapshot Policy OCID", "Snapshot Policy State",
		"Policy Lookup Status",
	])

	for region_subscription in regions:
		region_name = region_subscription.region_name
		print(f"Scanning region: {region_name}")
		region_config = dict(config, region=region_name)
		region_identity = oci.identity.IdentityClient(region_config)
		block_storage_client = oci.core.BlockstorageClient(region_config)
		file_storage_client = oci.file_storage.FileStorageClient(region_config)
		availability_domains = region_identity.list_availability_domains(tenancy_id).data
		volume_policy_cache = {}
		snapshot_policy_cache = {}

		boot_volume_count = 0
		boot_volume_policy_count = 0
		block_volume_count = 0
		block_volume_policy_count = 0
		filesystem_count = 0
		filesystem_policy_count = 0

		for compartment_id, compartment_name in compartment_names.items():
			block_volumes = oci.pagination.list_call_get_all_results(
				block_storage_client.list_volumes,
				compartment_id=compartment_id,
			).data
			boot_volumes = oci.pagination.list_call_get_all_results(
				block_storage_client.list_boot_volumes,
				compartment_id=compartment_id,
			).data

			for volume in block_volumes:
				block_volume_count += 1
				attached, policy_name, policy_id, lookup_status = resolve_volume_backup_policy(
					block_storage_client, volume.id, volume_policy_cache
				)
				if attached == "Yes":
					block_volume_policy_count += 1
				block_volume_sheet.append([
					region_name,
					compartment_name,
					volume.availability_domain,
					volume.display_name,
					volume.id,
					volume.lifecycle_state,
					volume.size_in_gbs,
					attached,
					policy_name,
					policy_id,
					lookup_status,
				])

			for boot_volume in boot_volumes:
				boot_volume_count += 1
				attached, policy_name, policy_id, lookup_status = resolve_volume_backup_policy(
					block_storage_client, boot_volume.id, volume_policy_cache
				)
				if attached == "Yes":
					boot_volume_policy_count += 1
				boot_volume_sheet.append([
					region_name,
					compartment_name,
					boot_volume.availability_domain,
					boot_volume.display_name,
					boot_volume.id,
					boot_volume.lifecycle_state,
					boot_volume.size_in_gbs,
					attached,
					policy_name,
					policy_id,
					lookup_status,
				])

			for availability_domain in availability_domains:
				filesystem_snapshot_policies = oci.pagination.list_call_get_all_results(
					file_storage_client.list_filesystem_snapshot_policies,
					compartment_id,
					availability_domain.name,
				).data
				policies_by_id = {
					policy.id: policy for policy in filesystem_snapshot_policies
				}
				filesystems = oci.pagination.list_call_get_all_results(
					file_storage_client.list_file_systems,
					compartment_id,
					availability_domain.name,
				).data

				for filesystem_summary in filesystems:
					filesystem_count += 1
					try:
						filesystem = file_storage_client.get_file_system(
							file_system_id=filesystem_summary.id
						).data
						policy_id = filesystem.filesystem_snapshot_policy_id
						if policy_id and policy_id not in snapshot_policy_cache:
							listed_policy = policies_by_id.get(policy_id)
							if listed_policy:
								snapshot_policy_cache[policy_id] = (
									listed_policy.display_name,
									listed_policy.lifecycle_state,
									"",
								)
						attached, policy_name, policy_state, lookup_status = (
							resolve_filesystem_snapshot_policy(
								file_storage_client,
								policy_id,
								snapshot_policy_cache,
							)
						)
					except oci.exceptions.ServiceError as exc:
						policy_id = ""
						attached = "Unknown"
						policy_name = ""
						policy_state = ""
						lookup_status = (
							f"File system detail lookup failed ({exc.status}): {exc.message}"
						)

					if attached == "Yes":
						filesystem_policy_count += 1
					filesystem_sheet.append([
						region_name,
						compartment_name,
						filesystem_summary.availability_domain or availability_domain.name,
						filesystem_summary.display_name,
						filesystem_summary.id,
						filesystem_summary.lifecycle_state,
						filesystem_summary.metered_bytes,
						attached,
						policy_name,
						policy_id,
						policy_state,
						lookup_status,
					])

		summary_sheet.append([
			region_name,
			boot_volume_count,
			boot_volume_policy_count,
			block_volume_count,
			block_volume_policy_count,
			filesystem_count,
			filesystem_policy_count,
		])
		print(
			f"  Found {boot_volume_count} boot volumes, {block_volume_count} block volumes, "
			f"and {filesystem_count} file systems"
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

	output_path = Path(__file__).with_name("Backup_Policy_Assignment_Inventory.xlsx")
	workbook.save(output_path)
	print(f"Inventory written to {output_path}")


if __name__ == "__main__":
	main()
