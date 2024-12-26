# OCI_Python
Repository for OCI Python

># Prerequisties
>Need to know about the API Fingerprints and adding all the fingerprints in config file

## 1. OCI IAM (Identity and Access Management)
OCI IAM is being evolved from the Identity to Identity with Domains.
Listed the diiferneces between the Identity with and without Domains in below figure.

![image](https://github.com/user-attachments/assets/e7c3dc20-8be4-46d9-881e-3bf6e39d5deb)

For more information on OCI IAM kindly refer the documentation provied by the Oracle Docs (https://docs.oracle.com/en-us/iaas/Content/Identity/home.htm)



The code I have written basically provides a gist on the backend api response of the IAM with and without domains.
The code that refers to IAM not in Identity Domain have to be federated with the IDCS provider then only it can give a wholesome experience.
The Identity Domain code mostly provides the basic operation of creation of user, adding the user to group, deletion of user & creation of group, adding users to the particular groups, deletion of group.
It has the ability to work on multiple tenancies to create the repetitive tasks rather than logging in to each tenancy and creation of users and groups.
