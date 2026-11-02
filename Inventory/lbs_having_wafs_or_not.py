import json
import oci
from pathlib import Path


config = oci.config.from_file()
identity = oci.identity.IdentityClient(config)
compartments = oci.pagination.list_call_get_all_results(
    identity.list_compartments,
    compartment_id=config['tenancy'],
    compartment_id_in_subtree=True,
    lifecycle_state='ACTIVE'
).data
compartment_names = {compartment.id: compartment.name for compartment in compartments}
compartment_names.setdefault(config['tenancy'], 'root')
regions = identity.list_region_subscriptions(config['tenancy']).data
report = {'regions': []}

for region in regions:
    region_name = region.region_name
    print(f"Checking region: {region_name}")
    config['region'] = region_name
    lb_client = oci.load_balancer.LoadBalancerClient(config)
    waf_client = oci.waf.WafClient(config)
    load_balancers = []
    deployed_wafs = []

    for compartment_id, compartment_name in compartment_names.items():
        print(f"Checking compartment: {compartment_name}")
        lb_results = oci.pagination.list_call_get_all_results(
            lb_client.list_load_balancers,
            compartment_id
        ).data
        for lb in lb_results:
            load_balancers.append({
                'id': lb.id,
                'display_name': lb.display_name,
                'compartment_name': compartment_name,
                'lifecycle_state': lb.lifecycle_state
            })

        waf_results = oci.pagination.list_call_get_all_results(
            waf_client.list_web_app_firewalls,
            compartment_id
        ).data
        for waf in waf_results:
            deployed_wafs.append({
                'id': waf.id,
                'display_name': waf.display_name,
                'compartment_name': compartment_name,
                'backend_type': waf.backend_type,
                'lifecycle_state': waf.lifecycle_state,
                'policy_id': waf.web_app_firewall_policy_id,
                'load_balancer_id': getattr(waf, 'load_balancer_id', None)
            })

    load_balancer_ids = {lb['id'] for lb in load_balancers}
    for lb in load_balancers:
        attached_wafs = [
            waf for waf in deployed_wafs
            if waf['backend_type'] == 'LOAD_BALANCER'
            and waf['load_balancer_id'] == lb['id']
        ]
        lb['waf_attached'] = bool(attached_wafs)
        lb['wafs'] = attached_wafs

    unused_wafs = [
        waf for waf in deployed_wafs
        if waf['backend_type'] == 'LOAD_BALANCER'
        and waf['lifecycle_state'] == 'ACTIVE'
        and waf['load_balancer_id'] not in load_balancer_ids
    ]
    report['regions'].append({
        'region': region_name,
        'load_balancers': load_balancers,
        'deployed_wafs': deployed_wafs,
        'unused_load_balancer_wafs': unused_wafs
    })

output_file = Path(__file__).with_name('WAF_Load_Balancer_Report.json')
with open(output_file, 'w', encoding='utf-8') as report_file:
    json.dump(report, report_file, ensure_ascii=False, indent=2)

print(f"Report written to {output_file}")
