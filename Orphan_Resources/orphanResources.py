
import oci
import pandas as pd

config = oci.config.from_file()

identity_client = oci.identity.IdentityClient(config)

compartments = identity_client.list_compartments(config["tenancy"], compartment_id_in_subtree=True, lifecycle_state='ACTIVE').data

regions = identity_client.list_region_subscriptions(config["tenancy"]).data
region_names = [region.region_name for region in regions]

def find_orphan_volumes(config, region_names, compartments):

    print("Finding orphan block volumes and boot volumes...")

    """Find unattached block volumes."""
    orphan_block_volumes = []
    orphan_boot_volumes = []

    orphan_block_volumes.append(("Region", "Block Volume Name", "Block Volume OCID", "Compartment Name"))
    orphan_boot_volumes.append(("Region", "Boot Volume Name", "Boot Volume OCID", "Compartment Name"))

    for region in region_names:
        print(f"Checking region: {region}")
        config["region"] = region

        identity_client = oci.identity.IdentityClient(config)
        ad_names = [ad.name for ad in identity_client.list_availability_domains(config["tenancy"]).data]

        for ad in ad_names:

            # Checking root compartment
            block_storage_client = oci.core.BlockstorageClient(config)
            compute_client = oci.core.ComputeClient(config)
            root_blk_volumes_list = oci.pagination.list_call_get_all_results(block_storage_client.list_volumes,compartment_id=config["tenancy"], availability_domain=ad).data
            for blk_vol in root_blk_volumes_list:
                blk_vol_attachments = compute_client.list_volume_attachments(compartment_id=config["tenancy"], availability_domain=ad, volume_id=blk_vol.id).data
                if not blk_vol_attachments:
                    orphan_block_volumes.append((config['region'], blk_vol.display_name, blk_vol.id, "Root"))

            root_boot_volumes_list = oci.pagination.list_call_get_all_results(block_storage_client.list_boot_volumes, compartment_id=config["tenancy"], availability_domain=ad).data
            for boot_vol in root_boot_volumes_list:
                boot_vol_attachment = compute_client.list_boot_volume_attachments(availability_domain=ad, compartment_id=config["tenancy"], boot_volume_id=boot_vol.id).data
                if not boot_vol_attachment:
                    orphan_boot_volumes.append((config['region'], boot_vol.display_name, boot_vol.id, "Root"))

            # For other compartments
            for cmp in compartments:
                blk_volumes_list = oci.pagination.list_call_get_all_results(block_storage_client.list_volumes,compartment_id=cmp.id, availability_domain=ad).data
                for blk_vol in blk_volumes_list:
                    blk_vol_attachments = compute_client.list_volume_attachments(compartment_id=cmp.id, availability_domain=ad, volume_id=blk_vol.id).data
                    if not blk_vol_attachments:
                        orphan_block_volumes.append((config['region'], blk_vol.display_name, blk_vol.id, cmp.name))

                boot_volumes_list = oci.pagination.list_call_get_all_results(block_storage_client.list_boot_volumes, compartment_id=cmp.id, availability_domain=ad).data    
                for boot_vol in boot_volumes_list:
                    boot_vol_attachment = compute_client.list_boot_volume_attachments(availability_domain=ad, compartment_id=cmp.id, boot_volume_id=boot_vol.id).data
                    if not boot_vol_attachment:
                        orphan_boot_volumes.append((config['region'], boot_vol.display_name, boot_vol.id, cmp.name))

    return orphan_block_volumes, orphan_boot_volumes

def orphan_load_balancers(config, region_names, compartments):

    print("Finding orphan load balancers...")

    lb_client = oci.load_balancer.LoadBalancerClient(config)
    orphan_load_balancers = []
    orphan_load_balancers.append(("Region", "Load Balancer Name", "Load Balancer OCID", "Compartment Name"))

    for region in region_names:
        print(f"Checking region: {region}")
        config["region"] = region

        # For root compartment
        root_lb_list = oci.pagination.list_call_get_all_results(lb_client.list_load_balancers, compartment_id=config["tenancy"]).data
        if root_lb_list:
            for lb in root_lb_list:
                backend_sets = lb_client.list_backend_sets(load_balancer_id=lb.id).data
                if backend_sets == []:
                    orphan_load_balancers.append((config['region'], lb.display_name, lb.id, "Root"))

                for backend_set in backend_sets:
                    backends = backend_set.backends
                    if backends == []:
                        orphan_load_balancers.append((config['region'], lb.display_name, lb.id, "Root"))

        # For other compartments
        for cmp in compartments:
            lb_list = oci.pagination.list_call_get_all_results(lb_client.list_load_balancers, compartment_id=cmp.id).data
            if lb_list:
                for lb in lb_list:
                    backend_sets = lb_client.list_backend_sets(load_balancer_id=lb.id).data
                    if backend_sets == []:
                        orphan_load_balancers.append((config['region'], lb.display_name, lb.id, cmp.name))

                    for backend_set in backend_sets:
                        backends = backend_set.backends
                        if backends == []:
                            orphan_load_balancers.append((config['region'], lb.display_name, lb.id, cmp.name))
    
    return orphan_load_balancers

def orphan_public_ips(config, region_names, compartments):

    print("Finding orphan public IPs...")

    virtual_network_client = oci.core.VirtualNetworkClient(config)
    orphan_ips = []
    orphan_ips.append(("Region", "Public IP", "Compartment Name"))

    for region in region_names:
        print(f"Checking region: {region}")
        config["region"] = region

        for compartment in compartments:
            reserved_public_ips = oci.pagination.list_call_get_all_results(
                virtual_network_client.list_public_ips,
                compartment_id=compartment.id,
                scope="REGION",
                lifetime="RESERVED"
            ).data

            for ip in reserved_public_ips:
                if ip.lifecycle_state == "AVAILABLE":
                    orphan_ips.append((config['region'], ip.ip_address, compartment.name))

            ephimeral_public_ips = oci.pagination.list_call_get_all_results(
                virtual_network_client.list_public_ips,
                compartment_id=compartment.id,
                scope="REGION",
                lifetime="EPHEMERAL"
            ).data

            for ip in ephimeral_public_ips:
                if ip.lifecycle_state == "AVAILABLE":
                    orphan_ips.append((config['region'], ip.ip_address, compartment.name))

    return orphan_ips

if __name__ == '__main__':
    orphans_block_volumes_details, orphans_boot_volumes_details = find_orphan_volumes(config, region_names, compartments)
    orphan_load_balancers_details = orphan_load_balancers(config, region_names, compartments)
    orphan_public_ips_details = orphan_public_ips(config, region_names, compartments)

    df1 = pd.DataFrame(orphans_block_volumes_details)
    df2 = pd.DataFrame(orphans_boot_volumes_details)
    df3 = pd.DataFrame(orphan_load_balancers_details)
    df4 = pd.DataFrame(orphan_public_ips_details)

    print("Writing Orphan resources details to excel file...")

    with pd.ExcelWriter(f"Orphan_Resources.xlsx") as writer:
        df1.to_excel(writer, sheet_name="Orphan Block Volumes", index=False)
        df2.to_excel(writer, sheet_name="Orphan Boot Volumes", index=False)
        df3.to_excel(writer, sheet_name="Orphan Load Balancers", index=False)
        df4.to_excel(writer, sheet_name="Orphan Public IPs", index=False)

    print("Orphan resources details are saved in excel file.")
