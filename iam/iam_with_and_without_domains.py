import oci
import re
from typing import Optional

class IdentityDomainClient:
    def __init__(self,config,service_endpoint):
        self.service_endpoint = service_endpoint
        self.config = config
        self.identity_domain_client = oci.identity_domains.IdentityDomainsClient(self.config,self.service_endpoint)

    
    #Checking if user is already present or not
    def check_user(self,email):
        try:
            is_present = False
            users = self.identity_domain_client.list_users(count=1000,attributes = ['user_name']).data
            for user in users.resources:
                if user.user_name == email:
                    print(f'{email} User already present')
                    is_present = True
            return is_present
        
        except Exception as e:
            print(f'Error is {e}')
    

    #Creating the user
    def user_create(self,email,username_as_email:Optional[bool] = True,username:Optional[str] = ''):
        """
        Creates a user in OCI Identity Domain.

        Args:
            email (str): Email of the user.
            username_as_email (bool): Whether to use email as username.
            username (str): Custom username if `username_as_email` is False.
        """

        is_user_present = self.check_user(email)
        if not is_user_present:
            try:
                #Getting the names from the email rather than typing the name fields again
                dot_index = email.index('.')
                special_index = email.index('@')

                #Additional field for monitoring users
                username = username if not username_as_email else email

                if dot_index<special_index:
                    given_name = email[:dot_index]
                    family_name = email[dot_index+1:special_index]
                else:
                    given_name = email[:special_index]
                    family_name = input('Enter last name: ')

                description = input(f'Enter the description for {email} user: ')

                #User creation logic
                user = self.identity_domain_client.create_user(
                    user = oci.identity_domains.models.User(
                        name = oci.identity_domains.models.UserName(
                            family_name = family_name ,
                            given_name = given_name,
                        ),
                    emails=[ oci.identity_domains.models.UserEmails(
                                value=email, type="work", primary=True
                            ),
                            oci.identity_domains.models.UserEmails(value=email, type="home"),
                           ],
                    user_name = username,
                    display_name = given_name+' '+family_name,
                    schemas = ["urn:ietf:params:scim:schemas:core:2.0:User"],
                    description = description,
                    )
                ).data
                print('{} created successfully'.format(user.user_name))

                #Adding user to Group
                print("Do you want to add this user into a group that is present already? \n Choose from the below options: \n 1. Yes \n 2. No")
                group_present = input('Enter the option 1 or 2: ').strip()
                match group_present:
                    case '1':
                        self.add_user_to_group(email,user.id)
                    case '2':
                        self.group_create(email,user.id)

            except Exception as e:
                print("Error is ", e)

            
    #Checking if Group is present or not
    def check_group(self,group_name):
        try:
            is_present = False
            groups = self.identity_domain_client.list_groups(
                count = 1000,
                attributes = ['displayName',]
            ).data
            for group in groups.resources:
                if group.display_name == group_name:
                    is_present=True
                    print('Group is already present')
                    break
            return is_present
        
        except Exception as e:
            print(f'Error is {e}')


    #Creating the Group
    def group_create(self,email,user_id):
        try:
            group_name = input('Enter the group name to be created: ')
            is_group_present = self.check_group(group_name)
            if not is_group_present:
                group = self.identity_domain_client.create_group(
                    group = oci.identity_domains.models.Group(
                    display_name = group_name, schemas=["urn:ietf:params:scim:schemas:core:2.0:Group"]
                    )
                ).data
    
                print(f"{group_name} Group created successfully")
                self.add_user_to_group(email,user_id,group_name,group.id)
            
        except Exception as e:
            print(f'Error is {e}')
            

    #Getting Group Ocid
    def get_group_info(self):
        try:
            groups_info = self.identity_domain_client.list_groups(
                count = 1000
            ).data
            print('Group Name displayed are as follows: ')
            for group in groups_info.resources:
                print(group.display_name)
            group_name = input('Enter the group name as displaed: ')
            group_ocid = ''
            for group in groups_info.resources:
                if group_name == group.display_name:
                    group_ocid = group.ocid
                    break
            return group_ocid,group_name
        
        except Exception as e:
            print(f'Error is {e}')
    
    #Adding User to group #### Using User SCIM ID not OCID
    def add_user_to_group(self,email,user_id, group_name: Optional[str] = '', group_id : Optional[str] = ''):
        try:

            if not group_name and not group_id:
                group_id,group_name = self.get_group_info()
            user_id = user_id
            user_in_group = False

            group_members = self.identity_domain_client.get_group(
                    group_id = group_id,
                    attributes='members',
                    attribute_sets=['request']
                    ).data

            if group_members.members:
                for member in group_members.members:
                    if user_id == member.value:
                        print("User already in group")
                        user_in_group = True
                        break
                    
            if not user_in_group:
                user_add_group = self.identity_domain_client.patch_group(
                    group_id = group_id,
                    patch_op = oci.identity_domains.models.PatchOp(
                        schemas = ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                        operations = [
                            {
                                "op": "add",
                                "path": "members",
                                "value": [{"value": user_id, "type": "User"}],
                            }
                        ],
                    )
                ).data

                print('User ',email,' successfully added to group ',group_name)
            
        except Exception as e:
            print(f'Error is {e}')


    #Deleting the User using SCIM ID , but we can use OCID too...    
    def del_user(self,email):
        #if user is associated with group
        try:
            user_response = self.identity_domain_client.list_users(attributes=['groups'], attribute_sets=['request']).data
            user_id = ''
            group_info = []
            for user in user_response.resources:
                if user.user_name == email:
                    user_id = user.id
                    for group in user.groups:
                        group_info.append((group.value,group.display))
                    break
                

            #Removing the user from group
            for group_id,group_name in group_info:
                self.identity_domain_client.patch_group(
                            group_id,
                            patch_op=oci.identity_domains.models.PatchOp(
                                schemas=["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                            operations=[
                                {
                                    "op": "remove",
                                    "path": "members",
                                    "value": [{"value": user_id, "type": "User"}],
                                }
                            ],
                        ),
                    )
                print(f'The User {email} is successfully removed from group {group_name}.')
        except :
            print(f'User {email} is already removed from all groups')
        
        try:
            #Deleting the user
            print(f'User {email} is going to delete ...')
            self.identity_domain_client.delete_user(user_id)
            print('Successfully deleted User')
        
        except Exception as e:
            print(f'Error is {e}')

    
    #Deleting the Group
    def del_group(self):
        groups_response = self.identity_domain_client.list_groups(attributes= 'members',attribute_sets = ['request']).data
        group_id = ''
        group_name = ''
        try:
            for group in groups_response.resources:
                print(group.display_name)
                choice = input('Enter yes/no for the deletion of the above group: ').lower()
                if choice == 'yes':
                    group_id = group.id
                    group_name = group.display_name
                    for user in group.members:
                        self.identity_domain_client.patch_group(
                                group_id,
                                patch_op=oci.identity_domains.models.PatchOp(
                                    schemas=["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                                operations=[
                                    {
                                        "op": "remove",
                                        "path": "members",
                                        "value": [{"value": user.value, "type": "User"}],
                                    }
                                ],
                            ),
                        )
                        print(f'The User {user.name} is successfully removed from group {group.display_name}.')
                    break

        except:
            print('There are no users in the group present')

        try:
            print(f'Group {group_name} is going to delete...')
            self.identity_domain_client.delete_group(group_id)
            print('Group Deleted Successfully')
        except Exception as e:
            print(f'Excepection is {e}')


#IAM not in Identity Domains:
class IdentityClient():
    def __init__(self,config):
        self.config = config
        self.identity_client = oci.identity.IdentityClient(self.config)
    
    def user_create(self,email,username_as_email:Optional[bool] = True,username:Optional[str] = ''):
        """
        Creates a user in OCI Identity Domain.

        Args:
            email (str): Email of the user.
            username_as_email (bool): Whether to use email as username.
            username (str): Custom username if `username_as_email` is False.
        """
        try:
            user_info = oci.pagination.list_call_get_all_results(self.identity_client.list_users,self.config['tenancy']).data
            is_user_present = False
            for user in user_info:
                if email in user.name:
                    print('user already present')
                    is_user_present = True
                    break
                
            if not is_user_present:
                username = username if not username_as_email else email
                user_description = input('Enter a description for the user to add: ')
                print('User creation is in progress....')
                user = self.identity_client.create_user(
                    create_user_details=oci.identity.models.CreateUserDetails(
                    compartment_id = self.config['tenancy'],
                    name = username,
                    description = user_description,
                    email = email
                    )
                ).data
                print(f'User {email} is successfully created.')

                print("Do you want to add this user into a group that is present already? \n Choose from the below options: \n 1. Yes \n 2. No")
                group_present = input('Enter the option 1 or 2: ')

                match group_present:
                    case '1':
                        self.add_user_to_group(email,user_id=user.id)
                    case '2':
                        self.group_create(email,user_id=user.id)

        except Exception as e:
            print(f'Error is {e}')


    def get_group_info(self):
        try:
            print('Group names are displayed: ')
            group_info = oci.pagination.list_call_get_all_results(self.identity_client.list_groups,self.config['tenancy']).data
            for group in group_info:
               print(f'{group.name}')
            group_name = input('Enter the group name as displayed: ')

            group_ocid = ''
            for group in group_info:
                if group_name == group.name:
                    group_ocid = group.id
                    break
            return (group_ocid,group_name)

        except Exception as e:
            print(f'Error is {e}')
    
    def add_user_to_group(self,email,user_id, group_name: Optional[str] = '', group_id : Optional[str] = ''):
        try:
            if not group_name and not group_id:
                group_id,group_name = self.get_group_info()

            user_id = user_id
            user_in_group = False
            group_membership_details = self.identity_client.list_user_group_memberships(compartment_id=self.config['tenancy'],group_id=group_id).data
            for membership in group_membership_details:
                if membership.user_id == user_id:
                    user_in_group=True
                    print(f'User {email} already in group')
                    break

            if not user_in_group:   
                print(f'Adding {email} User to {group_name} Group')     
                assign_user_to_group = self.identity_client.add_user_to_group(
                    add_user_to_group_details=oci.identity.models.AddUserToGroupDetails(
                        user_id = user_id,
                        group_id = group_id
                        )
                    ).data

                print(f'{email} User assigned to {group_name} Group successfully')

        except Exception as e:
            print(f'Error is {e}')


    def group_create(self,email,user_id):
        try:
            print('Groups present are:')
            groups_info = self.identity_client.list_groups(compartment_id=self.config['tenancy']).data
            for group in groups_info:
                print(group.name)
            group_name = input('Enter the group name other than the above groups present: ').strip()
            description = input('Enter the description for the group to create: ')
            print(f'{group_name} Group creation is in progess....')
            group = self.identity_client.create_group(
                create_group_details=oci.identity.models.CreateGroupDetails(
                    compartment_id = self.config['tenancy'],
                    name = group_name,
                    description = description
                )
            ).data
            print(f'{group_name} Group is created successfully')
            self.add_user_to_group(email,user_id,group_name=group_name,group_id=group.id)

        except Exception as e:
            print(f'Error is {e}')

    def del_user(self,email):
        try:    
            user_ocid = ''
            user_details = oci.pagination.list_call_get_all_results(self.identity_client.list_users,self.config['tenancy']).data
            for user in user_details:
                if email in user.name:
                    user_ocid = user.id
                    break
            
            group_membership_details = self.identity_client.list_user_group_memberships(compartment_id=self.config['tenancy'],user_id =user_ocid).data
            if group_membership_details:
                for membership in group_membership_details:
                    group_info = self.identity_client.get_group(group_id=membership.group_id).data
                    print(f'{email} User is being removed from {group_info.name}')
                    self.identity_client.remove_user_from_group(user_group_membership_id=membership.id)
                    print(f'{email} User successfully removed from the {group_info.name}')
            else:
                print(f'{email} User is not present in any Group.')
            print(f'{email} User deletion is in progress....')
            self.identity_client.delete_user(user_id=user_ocid)
            print(f'{email} User is successfully deleted')
        
        except Exception as e:
            print(f'Error is {e}')

    def del_group(self):
        try:
            print('Groups names are displayed below:')
            group_info = self.identity_client.list_groups(compartment_id=self.config['tenancy']).data
            for group in group_info:
                print(group.name)

            group_name = input('Enter the group name as displayed: ')
            group_ocid = ''
            for group in group_info:
                if group_name==group.name:
                    group_ocid = group.id
                    break

            group_membership_details = self.identity_client.list_user_group_memberships(compartment_id=self.config['tenancy'],group_id=group_ocid).data
            if group_membership_details:
                for membership in group_membership_details:
                    user_info = self.identity_client.get_user(user_id = membership.user_id).data
                    print(f'{user_info.name} User is being removed from {group_name}')
                    self.identity_client.remove_user_from_group(user_group_membership_id=membership.id)
                    print(f'{user_info.name} User successfully removed from the {group_name}')
                else:
                    print(f'No Users in {group_name} Group')

            print(f'{group_name} Group deletion is in progress....')
            self.identity_client.delete_group(group_id=group_ocid)
            print(f'{group_name} Group is successfully deleted.')
        
        except Exception as e:
            print(f'Error is {e}')


#Getting the profiles in config
def get_profile_names():
    try:
        config = ''
        with open('/home/codespace/.oci/config','r') as config_file:
            config = config_file.read()

        profiles = re.findall(r'\[(.*?)\]', config)
        profile_names = []

        multiple_tenancies_or_not = input('Enter if you want to create the users in multiple tenancies? \nChoose the options 1 or 2 \n1. Yes \n2. No \n ')
        if multiple_tenancies_or_not == '1':
            print('The profiles in the config file are as below: ')
            for profile in profiles:
                if profile == 'DEFAULT':
                    print(profile,' -- SANDBOX')
                else:
                    print(profile)
                print("1. Add this profile name \n 2. No don't add this profile")
                select_profile = input('Enter the option 1 or 2: ')
                if select_profile == '1':
                    profile_names.append(profile)
            return profile_names

        elif multiple_tenancies_or_not == '2':
            print('The profiles in the config file are as below: ')
            for profile in profiles:
                if profile == 'DEFAULT':
                    print(profile,' --> SANDBOX')
                else:
                    print(profile)
            profile_name = input('Enter the profile name as displayed: ')
            profile_names.append(profile_name)
            return profile_names
        
    except Exception as e:
        print(f'Error is {e}')

#For Identity Domain User
def iam_in_identity_domain():
    try:
        profile_names = get_profile_names()
        for profile in profile_names:
            config = oci.config.from_file(profile_name=profile)
            identity_client = oci.identity.IdentityClient(config)
            identity_domain = identity_client.list_domains(compartment_id=config['tenancy']).data
            identity_domain_client = IdentityDomainClient(config,identity_domain[0].url)
            while True:
                print("Welcome to the User, Group creation and deletion in Identity Domains")
                choice = input('Enter the operation you want to perform \n1. User creation \n2. User delete \n3. Group deletion \n4. Exit \n')
                match choice:
                    case '1':
                        email = input('Enter the email id: ')
                        print('Do you want to keep username as email? ')
                        option = input('Enter yes or no: ').lower()
                        match option:
                            case 'yes':
                                identity_domain_client.user_create(email)
                            case 'no':
                                username = input('Enter Username: ')
                                username_as_email = False
                                identity_domain_client.user_create(email,username_as_email,username)

                    case '2':
                        email = input('Enter the email id: ')
                        identity_domain_client.del_user(email)

                    case '3':
                        identity_domain_client.del_group()

                    case '4':
                        exit()

                    case default:
                        print('Enter the options available above')
            

    except Exception as e:
        print(f'Error is {e}')


#For Identity User 
def iam_not_in_identity_domain():
    try:
        profile_names = get_profile_names()
        for profile in profile_names:
            config = oci.config.from_file(profile_name=profile)
            identity_client = IdentityClient(config)
            while True:
                print("Welcome to the User CRUD & Group Delete in Identity")
                choice = input('Enter the operation you want to perform \n1. User creation \n2. User delete \n3. Group deletion \n4. Exit \n')
                match choice:
                    case '1':
                        email = input('Enter the email id: ')
                        print('Do you want to keep username as email? ')
                        option = input('Enter yes or no: ').lower()
                        match option:
                            case 'yes':
                                identity_client.user_create(email)
                            case 'no':
                                username = input('Enter Username: ')
                                username_as_email = False
                                identity_client.user_create(email,username_as_email,username)

                    case '2':
                        email = input('Enter the email id: ')
                        identity_client.del_user(email)

                    case '3':
                        identity_client.del_group()

                    case '4':
                        exit()

                    case default:
                        print('Enter the options available above')

    except Exception as e:
        print('Error is {e}')


#Starts here .... .....

print('Choose from the options below: \n 1. IAM in Identity Domains \n 2. IAM not in Identity Domains ')
choice = input("Enter the option: ")
match choice:
    case '1':
        iam_in_identity_domain()
    case '2':
        iam_not_in_identity_domain()
    case default:
        print('Choose the correct option')