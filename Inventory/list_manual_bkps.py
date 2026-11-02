import oci
from openpyxl import Workbook
from datetime import datetime, timedelta
import time

# Create a new Excel workbook
wb = Workbook()

#Add profile_name
profiles = ['']

# Remove the default sheet created by Workbook if it exists
if "Sheet" in wb.sheetnames:
    default_sheet = wb["Sheet"]
    wb.remove(default_sheet)

# For cost calculation
def cost_calculation(config, resource_ocid):
    time_to = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    time_from = time_to - timedelta(days=1)
    config['region'] = 'me-jeddah-1'
    usage = oci.usage_api.UsageapiClient(config)
    request_details = oci.usage_api.models.RequestSummarizedUsagesDetails(
        tenant_id=config['tenancy'],
        time_usage_started=time_from,
        time_usage_ended=time_to,
        granularity='DAILY',
        is_aggregate_by_time=True,
        query_type='COST',
        filter=oci.usage_api.models.Filter(
            operator="AND",
            dimensions=[{'key': 'resourceId', 'value': resource_ocid}]
        )
    )
    for attempt in range(4):
        try:
            request_usage = usage.request_summarized_usages(
                request_summarized_usages_details=request_details
            ).data
            break
        except oci.exceptions.ServiceError as exc:
            if exc.status != 429:
                raise
            if attempt == 3:
                print(f"Cost unavailable after repeated 429 responses for {resource_ocid}")
                return -1, 'USD'
            retry_after = exc.headers.get('retry-after')
            try:
                delay = max(1.0, min(float(retry_after), 60.0))
            except (TypeError, ValueError):
                delay = min(2 ** (attempt + 1), 30)
            print(f"Usage API rate limited; retrying {resource_ocid} in {delay:g} seconds")
            time.sleep(delay)

    if request_usage.items == []:
        return 0,'USD'
    else:
        return request_usage.items[0].attributed_cost, request_usage.items[0].currency

# Loop over each profile and create a new sheet in the same workbook
for profile_name in profiles:
    # Set up OCI config for the current profile
    config = oci.config.from_file(profile_name=profile_name)
    result = []
    print(f"Fetching data for profile: {profile_name}")

    # OCI client setup
    identity_client = oci.identity.IdentityClient(config)
    compartments = oci.pagination.list_call_get_all_results(identity_client.list_compartments, compartment_id=config['tenancy'], compartment_id_in_subtree=True).data
    volume_client = oci.core.BlockstorageClient(config)

    #listing regions
    regions = identity_client.list_region_subscriptions(config["tenancy"]).data
    region_names = [region.region_name for region in regions]

    for region in region_names:
        print(f"Checking region: {region}")
        config['region'] = region


        # Fetch boot and block volume backups
        for compartment in compartments:
            print(f"Checking compartment: {compartment.name}")
            boot_volume_backups = oci.pagination.list_call_get_all_results(volume_client.list_boot_volume_backups, compartment.id).data
            block_volume_backups = oci.pagination.list_call_get_all_results(volume_client.list_volume_backups, compartment.id).data

            # Collect backup data
            for boot_volume_backup in boot_volume_backups:
                if boot_volume_backup.source_type == 'MANUAL':
                    created_date = boot_volume_backup.time_created.strftime("%Y-%m-%d")

                    try:
                        source_volume_name = volume_client.get_boot_volume(
                            boot_volume_id=boot_volume_backup.boot_volume_id
                        ).data.display_name
                    except oci.exceptions.ServiceError as exc:
                        print(f"Boot volume lookup failed ({exc.status}): {exc.message}")
                        source_volume_name = (
                            'Source Volume Deleted!!!!' if exc.status == 404
                            else 'Source Volume Details Unavailable'
                        )
                    cost, currency = cost_calculation(config, boot_volume_backup.id)
                    result.append((compartment.name, region, boot_volume_backup.id, source_volume_name, boot_volume_backup.display_name, boot_volume_backup.unique_size_in_gbs, boot_volume_backup.defined_tags['Oracle-Tags']['CreatedBy'], created_date, cost, currency))

            for block_volume_backup in block_volume_backups:
                if block_volume_backup.source_type == 'MANUAL':
                    created_date = block_volume_backup.time_created.strftime("%Y-%m-%d")
                    try:
                        source_volume_name = volume_client.get_volume(
                            volume_id=block_volume_backup.volume_id
                        ).data.display_name
                    except oci.exceptions.ServiceError as exc:
                        print(f"Block volume lookup failed ({exc.status}): {exc.message}")
                        source_volume_name = (
                            'Source Volume Deleted!!!!' if exc.status == 404
                            else 'Source Volume Details Unavailable'
                        )
                    cost, currency = cost_calculation(config, block_volume_backup.id)
                    result.append((compartment.name, region, block_volume_backup.id, source_volume_name, block_volume_backup.display_name, block_volume_backup.unique_size_in_gbs, block_volume_backup.defined_tags['Oracle-Tags']['CreatedBy'], created_date, cost, currency))

    # Create a new sheet for each profile
    ws = wb.create_sheet(title=profile_name)

    # Add headers to the sheet
    headers = ["Compartment Name", "Region Name", "Backup Volume ID", "Source Volume Name", "Backup Name", "Size in GBs", "Created by", "Creation Date", "No. of Days", "Cost / Day", "Currency Type"]
    ws.append(headers)

    # Get the current date to calculate the number of days
    current_date = datetime.now()

    # Write the data to the sheet
    for row in result:
        compartment_name, region, backup_volume_id, source_volume_name, backup_name, size_in_gbs, created_by, creation_date_str, cost, currency = row
        creation_date = datetime.strptime(creation_date_str, "%Y-%m-%d")
        days_since_creation = (current_date - creation_date).days
        ws.append([compartment_name, region, backup_volume_id, source_volume_name, backup_name, size_in_gbs, created_by, creation_date_str, days_since_creation, cost, currency])

# Save the workbook with all profile sheets
wb.save("Backup_Updated_Data.xlsx")

print("Data has been written to 'Backup_Updated_Data.xlsx'")
