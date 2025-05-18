import oci
import io
import json
from fdk import response

# Function to publish notification
def publish_notification(topic_id, msg_body, vm_name):
    signer = oci.auth.signers.get_resource_principals_signer()
    client = oci.ons.NotificationDataPlaneClient({}, signer=signer)

    # Define a message title
    msg_title = f"Alert from VM: {vm_name}"
    
    # Create a message object with title and body
    msg = oci.ons.models.MessageDetails(title=msg_title, body=msg_body)
    print(msg, flush=True)

    # Publish the message to the topic
    client.publish_message(topic_id, msg)


# Function to fetch instance details (private IPs)
def get_ip_details(instance_id):
    signer = oci.auth.signers.get_resource_principals_signer()
    try:
        # Use signer instead of config for resource principals
        compute_client = oci.core.ComputeClient({}, signer=signer)
        virtual_network_client = oci.core.VirtualNetworkClient({}, signer=signer)

        # Get instance details and VNIC attachments
        instance = compute_client.get_instance(instance_id).data
        vnic_attachments = oci.pagination.list_call_get_all_results(
            compute_client.list_vnic_attachments,
            compartment_id=instance.compartment_id,
            instance_id=instance_id
        ).data

        instance_info = {'private_ips': []}

        for attachment in vnic_attachments:
            vnic = virtual_network_client.get_vnic(attachment.vnic_id).data

            # Get private IPs for each VNIC
            private_ips = oci.pagination.list_call_get_all_results(
                virtual_network_client.list_private_ips,
                vnic_id=vnic.id
            ).data

            instance_info['private_ips'].extend([ip.ip_address for ip in private_ips])

        print("IPs added successfully", flush=True)

        if instance_info["private_ips"]:
            return str(instance_info["private_ips"][0])
        else:
            return "No IP found"
    except Exception as ex:
        print('ERROR: Error in fetching instance details', ex, flush=True)
        raise


# Function handler function entry point whenever a function is called this function executes #first
def handler(ctx, data: io.BytesIO = None):
    try:
        body = json.loads(data.getvalue())
   
        # Fetch the instance ID
        instance_id = body[0]['oracle']['instanceid']
        body[0]["ip"] = get_ip_details(instance_id)

        topic_id = "ocid1.onstopic.oc1.ap-hyderabad-1.amaaaaaaiazeuoiapkq4v7rmtmx5zlrwzkcjrwhbjlrknyrqufstoao2roaa" #ONS topic OCID
        vm_name = body[0]['source']

        print('Fetched the values and processed the data accordingly', flush=True)
    except Exception as ex:
        print('ERROR: Missing key in payload or incorrect format', ex, flush=True)
        raise

    # Serialize the dictionary before sending it as the message body
    publish_notification(topic_id, json.dumps(body[0]), vm_name)

    return response.Response(
        ctx,
        response_data=json.dumps({"response": "email-sent"}),
        headers={"Content-Type": "application/json"}
    )
