import io
import json
import logging
import oci

from fdk import response

def get_oic_instanceState(oic_ocid):
    try:
        signer = oci.auth.signers.get_resource_principals_signer()
        oic_client = oci.integration.IntegrationInstanceClient(config={}, signer=signer)
        result = oic_client.get_integration_instance(integration_instance_id=oic_ocid).data

        return result.lifecycle_state
    
    except Exception as e:
        logging.getLogger().info('error ' + str(e))
        return "No_OIC_Instance_Found"

def oic_auto_start_and_stop(oic_ocid, action):
    try:
        signer = oci.auth.signers.get_resource_principals_signer()
        oic_client = oci.integration.IntegrationInstanceClient(config={}, signer=signer)
        get_oic_instance_state = get_oic_instanceState(oic_ocid)
        if get_oic_instance_state != 'No_OIC_Instance_Found':
            if action == 'STOP' and get_oic_instance_state == 'ACTIVE':
                oic_client.stop_integration_instance(integration_instance_id=oic_ocid)
                result = 'Successfully stopped the OIC Instance ' + str(oic_ocid)
                logging.getLogger().info(result)
                return result

            elif action == 'START' and get_oic_instance_state == 'INACTIVE':
                oic_client.start_integration_instance(integration_instance_id=oic_ocid)
                result = 'Successfully started the OIC Instance ' + str(oic_ocid)
                logging.getLogger().info(result)
                return result

            else:
                result = 'kindly check the OIC Instance Status and action type want to be performed ' + str(oic_ocid)
                logging.getLogger().info(result)
                return result

        else:
            result = "Kindly check the OIC OCID " + str(oic_ocid)
            return result

    except Exception as e:
        logging.getLogger().info('Kindly check the error '+ str(e))

def handler(ctx, data: io.BytesIO = None):

    try:
        body = json.loads(data.getvalue())
        action = body["action"] # string START or STOP
        oic_ocids = body["oic_ocids"]   # list
        results = []

        for i in range(len(oic_ocids)):
            oic_ocid = oic_ocids[i]
            msg = oic_auto_start_and_stop(oic_ocid,vs_ocid, action)
            results.append({
                "oic_ocid": oic_ocid,
                "result": str(msg)
            })

        
    except (Exception) as ex:
        logging.getLogger().info('error parsing json payload: ' + str(ex))

    
    return response.Response(
        ctx, response_data=json.dumps(
            {"message": results}),
        headers={"Content-Type": "application/json"}
    )
