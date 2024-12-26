import oci
from typing import Optional
import openpyxl
import threading


config = oci.config.from_file()

class ComputeInstanceCreation():
    def __init__(self,config):
        #Initializations of the main variables
        self.config = config
        self.identity_client = oci.identity.IdentityClient(config=self.config)
        self.compute_client = oci.core.ComputeClient(config=self.config)
        self.compute_client_composite_operations = oci.core.ComputeClientCompositeOperations(self.compute_client)
        self.virtual_client = oci.core.VirtualNetworkClient(config=self.config)
        self.volume_client = oci.core.BlockstorageClient(config=self.config)
        self.volume_client_composite_operations = oci.core.BlockstorageClientCompositeOperations(self.volume_client)
        self.root_ocid = config['tenancy']


    def get_compute_details(self,file_path):
        compute_data = openpyxl.load_workbook(filename=file_path)   
        sheet = compute_data['Compute_Instance_Details']

        def process_row(row):
            if row[0] is not None:
                self.create_compute_instance(
                    row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8],
                    row[9], row[10], row[11], float(row[12]), float(row[13]),
                    row[14], row[15], row[16], row[17], row[18], row[19]
                )

        threads = []  # List to keep track of threads

        for row in sheet.iter_rows(values_only=True, min_row=2):
            thread = threading.Thread(target=process_row, args=(row,))
            threads.append(thread)
            thread.start()

    # Wait for all threads to complete
        for thread in threads:
            thread.join()


    def fetch_cmp_ocid(self, cmp_name:Optional[str]=''):
        '''
        cmp_name = Compartment Name
        Pass the compartment name if you know, else leave it
        '''
        try:   
            cmp_ocid = ''
            compartments = self.identity_client.list_compartments(
                compartment_id=self.root_ocid, limit = 100,
                compartment_id_in_subtree = True, lifecycle_state = 'ACTIVE'
            ).data

            if not cmp_name:
                print('Compartment Names are as follows:')
                for compartment in compartments:
                    print(compartment.name)
                cmp_name = input('Enter the compartment name as displayed: ')

            for compartment in compartments:
                if compartment.name == cmp_name:
                    cmp_ocid = compartment.id
                    break
                
            return cmp_ocid
        
        except Exception as e:
            print(f'Error is {e}')
        

    def get_subnet_ocid(self,vcn_name:Optional[str]='',sn_name:Optional[str]='',cmp_ocid:Optional[str]=''):
        '''
        vcn_name = VCN Name
        sn_name = Subnet Name
        cmp_ocid = Compartment OCID
        Enter the VCN name, Subnet name & Compartment OCID if you know else leave it
        '''

        try:
            sn_ocid = ''
            vcn_ocid = ''
            if not cmp_ocid:
                cmp_ocid = self.fetch_cmp_ocid()

            vcns = self.virtual_client.list_vcns(compartment_id=cmp_ocid).data
            if not vcn_name:
                print('VCNS present are: ')
                for vcn in vcns:
                    print(vcn.display_name)
                vcn_name = input('Enter the VCN name as displayed: ')
                
            for vcn in vcns:
                if vcn.display_name == vcn_name:
                    vcn_ocid = vcn.id
                    break

            subnets = self.virtual_client.list_subnets(compartment_id=cmp_ocid,vcn_id = vcn_ocid).data
            
            if not sn_name:
                print('Subnet Names are Displayed Below:')
                for sn in subnets:
                    print(sn.display_name)
                sn_name = input('Enter the Subnet Name as displayed: ')
            
            for sn in subnets:
                if sn.display_name == sn_name:
                    sn_ocid = sn.id
                    break
            
            return sn_ocid

        
        except Exception as e:
            print(f'Error is {e}')
    

    def get_availability_domain_info(self,cmp_ocid:Optional[str]=''):
        '''
        cmp_ocid = Compartment OCID
        
        Returns (AD Name, AD ID)
        '''
        try:
            if not cmp_ocid:
                cmp_ocid = self.fetch_cmp_ocid()

            ad_ocid = ''
            ads = self.identity_client.list_availability_domains(compartment_id=cmp_ocid).data
            
            if len(ads)!=1:
                print('Availability Domains Present are as Follows:')
                for ad in ads:
                    print(ad.name)
                ad_name = input('Enter the AD Name as displayed: ')
                for ad in ads:
                    if ad_name == ad.name:
                        ad_ocid = ad.id
                        ad_name = ad.name
                        break
                
            else:
                ad_ocid = ads[0].id
                ad_name = ads[0].name
            return (ad_name,ad_ocid)

            
        
        except oci.exceptions.ServiceError as e:
            print(f'Error is {e}')

    def get_ssh_pub_key(self,keypath):
        '''
        keypath = Full path of the Public Key which ends with .pub
        Ex: pub.pub
        '''
        try:
            with open(keypath,mode='r') as file:
                pub_key_contents = file.read().strip()

            return pub_key_contents


        except Exception as e:
            print(f'Error is {e}')


    def is_image_shape_compatible(self,image_id,shape):
        '''
        image_id = Image ID of the image that you want to launch

        shape = Shape name
        Ex:VM.Standard.A1.Flex

        '''

        try:
            isCompatible = self.compute_client.get_image_shape_compatibility_entry(
                image_id =image_id,shape_name=shape).data

            if isCompatible:
                return True


        except Exception as e:
            print('NO shape compatible')
            return False
            # print(f'Error is {e}')
    
    
    
    def get_image_id(self,image_name,cmp_ocid:Optional[str]=''):
        '''
        cmp_ocid = Compartment OCID
        
        image_name = Actual display name of the Image which includes OS, Version, & remaining details
        Eg: Windows-Server-2022-Datacenter-Edition-BM-X9-2024.09.10-0
        '''

        try:
            if not cmp_ocid:
                cmp_ocid = self.fetch_cmp_ocid()

            images_info = oci.pagination.list_call_get_all_results(
                self.compute_client.list_images,
                cmp_ocid,
                display_name = image_name
            ).data

            images_id = images_info[0].id
            return images_id
            

        except Exception as e:
            print(f'Error is {e}')
    

    """def get_shape_name(self, ad_name, cmp_ocid:Optional[str]=''):
        '''
        ad_name = Availability domain Name
        Eg: KOeP:AP-HYDERABAD-1-AD-1

        cmp_ocid = Compartment OCID
        '''
        try:
            if not cmp_ocid:
                cmp_ocid = self.fetch_cmp_ocid()

            shapes_info = oci.pagination.list_call_get_all_results(
                self.compute_client.list_shapes,
                cmp_ocid,
                availability_domain = ad_name
                #image_id = image_ocid
            ).data

            for shape in shapes_info:    
                print(shape.shape)

        except Exception as e:
            print(f'Error is {e}')"""

    def create_compute_instance(self,display_name:str,is_win_instance:bool,\
                                resource_cmp_name:str,vcn_name:str,sn_name:str,sn_cmp_name:str,\
                                assign_pub_ip:bool,pvt_ip:str,img_cmp_name:str,image_name:str,shape:str,ocpus:float,\
                                memory:float,boot_vol_size_in_gbs:int,is_block_vol:bool,block_vol_name:str,\
                                block_vol_size:int,keypath:str,license_type:str):
        
        '''
        There are assumptions made while creating and attaching the block volume 
         1. "BALANCED Mode" i.e., 10 VPUs/GB
         2. Attachment Type = PARAVIRRTUALIZATION
         3. Encryption = Oracle managed keys
         4. Access type = Read/Write

         One can change accordingly.
        '''


        try:
            sn_cmp_id = self.fetch_cmp_ocid(cmp_name=sn_cmp_name)
            resource_cmp_id = self.fetch_cmp_ocid(cmp_name=resource_cmp_name)
            img_cmp_id = self.fetch_cmp_ocid(cmp_name=img_cmp_name)
            image_id = self.get_image_id(image_name=image_name,cmp_ocid=img_cmp_id)
            boot_vol = boot_vol_size_in_gbs
            is_shape_compatible_with_image = self.is_image_shape_compatible(image_id=image_id,shape=shape)
            if is_shape_compatible_with_image:
                sn_id = self.get_subnet_ocid(vcn_name=vcn_name,sn_name=sn_name,cmp_ocid=sn_cmp_id)
                ad_name,ad_ocid = self.get_availability_domain_info(cmp_ocid=resource_cmp_id)

                print(f'Creating Instance {display_name}')
                # FOR WINDOWS INSTANCE 
                if is_win_instance:

                    # FOR WINDOWS INSTANCE WITH BLOCK VOLUME
                    if is_block_vol:
                        create_compute_instance = self.compute_client_composite_operations.launch_instance_and_wait_for_state(
                            launch_instance_details=oci.core.models.LaunchInstanceDetails(
                                availability_domain = ad_name,
                                compartment_id = resource_cmp_id,
                                create_vnic_details = oci.core.models.CreateVnicDetails(
                                    assign_public_ip = assign_pub_ip,
                                    private_ip = pvt_ip,
                                    subnet_id = sn_id
                                ),
                                display_name = display_name,
                                image_id=image_id,
                                shape=shape,
                                shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
                                    ocpus=ocpus,
                                    memory_in_gbs=memory
                                ),
                                launch_volume_attachments = [
                                    oci.core.models.LaunchAttachParavirtualizedVolumeDetails(
                                        display_name = block_vol_name,
                                        is_read_only = False,
                                        is_shareable = False,
                                        launch_create_volume_details = oci.core.models.LaunchCreateVolumeFromAttributes(
                                            volume_creation_type = 'ATTRIBUTES',
                                            compartment_id = resource_cmp_id,
                                            display_name = block_vol_name,
                                            size_in_gbs = block_vol_size
                                        )
                                    )
                                ],
                                licensing_configs=[
                                    oci.core.models.LaunchInstanceWindowsLicensingConfig(
                                    type="WINDOWS",
                                    license_type = license_type)],
                                source_details = oci.core.models.InstanceSourceViaImageDetails(
                                        image_id=image_id,
                                        boot_volume_size_in_gbs = boot_vol
                               )
                            ),
                        wait_for_states = [oci.core.models.Instance.LIFECYCLE_STATE_RUNNING]
                        )

                    # FOR WINDOWS INSTANCE WITHOUT BLOCK VOLUME    
                    else:
                        create_compute_instance = self.compute_client_composite_operations.launch_instance_and_wait_for_state(
                            launch_instance_details=oci.core.models.LaunchInstanceDetails(
                                availability_domain = ad_name,
                                compartment_id = resource_cmp_id,
                                create_vnic_details = oci.core.models.CreateVnicDetails(
                                    assign_public_ip = assign_pub_ip,
                                    private_ip = pvt_ip,
                                    subnet_id = sn_id
                                ),
                                display_name = display_name,
                                image_id=image_id,
                                shape=shape,
                                shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
                                    ocpus=ocpus,
                                    memory_in_gbs=memory
                                ),
                                licensing_configs=[
                                    oci.core.models.LaunchInstanceWindowsLicensingConfig(
                                    type="WINDOWS",
                                    license_type = license_type)],
                                source_details = oci.core.models.InstanceSourceViaImageDetails(
                                        image_id=image_id,
                                        boot_volume_size_in_gbs = boot_vol
                               )
                            ),
                        wait_for_states = [oci.core.models.Instance.LIFECYCLE_STATE_RUNNING]
                        )

                # FOR LINUX INSTANCES
                else:
                    pub_key = self.get_ssh_pub_key(keypath=keypath)

                    # FOR LINUX INSTANCES WITH BLOCK VOLUME
                    if is_block_vol:
                        create_compute_instance = self.compute_client_composite_operations.launch_instance_and_wait_for_state(
                            launch_instance_details=oci.core.models.LaunchInstanceDetails(
                                availability_domain = ad_name,
                                compartment_id = resource_cmp_id,
                                create_vnic_details = oci.core.models.CreateVnicDetails(
                                    assign_public_ip = assign_pub_ip,
                                    private_ip = pvt_ip,
                                    subnet_id = sn_id
                                ),
                                display_name = display_name,
                                image_id=image_id,
                                shape=shape,
                                shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
                                    ocpus=ocpus,
                                    memory_in_gbs=memory
                                ),
                                metadata = {
                                    'ssh_authorized_keys': pub_key
                                },
                                launch_volume_attachments = [
                                    oci.core.models.LaunchAttachParavirtualizedVolumeDetails(
                                        display_name = block_vol_name,
                                        is_read_only = False,
                                        is_shareable = False,
                                        launch_create_volume_details = oci.core.models.LaunchCreateVolumeFromAttributes(
                                            volume_creation_type = 'ATTRIBUTES',
                                            compartment_id = resource_cmp_id,
                                            display_name = block_vol_name,
                                            size_in_gbs = block_vol_size
                                        )
                                    )
                                ],
                                source_details = oci.core.models.InstanceSourceViaImageDetails(
                                        image_id=image_id,
                                        boot_volume_size_in_gbs = boot_vol
                               )
                            ),
                            wait_for_states=[oci.core.models.Instance.LIFECYCLE_STATE_RUNNING]
                        )
                        
                    # FOR LINUX INSTANCES WITHOUT BLOCK VOLUME    
                    else:
                        create_compute_instance = self.compute_client_composite_operations.launch_instance_and_wait_for_state(
                            launch_instance_details=oci.core.models.LaunchInstanceDetails(
                                availability_domain = ad_name,
                                compartment_id = resource_cmp_id,
                                create_vnic_details = oci.core.models.CreateVnicDetails(
                                    assign_public_ip = assign_pub_ip,
                                    private_ip = pvt_ip,
                                    subnet_id = sn_id
                                ),
                                display_name = display_name,
                                image_id=image_id,
                                shape=shape,
                                shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
                                    ocpus=ocpus,
                                    memory_in_gbs=memory
                                ),
                                metadata = {
                                    'ssh_authorized_keys': pub_key
                                },
                                source_details = oci.core.models.InstanceSourceViaImageDetails(
                                        image_id=image_id,
                                        boot_volume_size_in_gbs = boot_vol
                               )
                            ),
                            wait_for_states=[oci.core.models.Instance.LIFECYCLE_STATE_RUNNING]
                        )
                print('Successfully Created Instance')
                print(f'Instance Name : {create_compute_instance.data.display_name}\n')
                print(f'Instance ID : {create_compute_instance.data.id}')    


        except Exception as e:
            print(f'Error is {e}')



file_path = input('Enter the path of the Compute Instances Details Excel Sheet: ')
compute_client = ComputeInstanceCreation(config)
compute_client.get_compute_details(file_path=file_path)
