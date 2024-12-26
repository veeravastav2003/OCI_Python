# COMPUTE INSTANCE CREATION

## Overview
This README provides guidance on using a Python script to automate the creation of compute instances in Oracle Cloud Infrastructure (OCI) using the OCI Python SDK. The script utilizes threading to enhance performance and reads input parameters from an Excel sheet. Additionally, it supports the creation of block volumes if necessary.

## Features
- Threading: The script implements threading to allow simultaneous instance creation, improving efficiency.
- Excel Input: All required parameters for instance creation are read from an Excel file.
- Block Volume Creation: Optionally creates block volumes as specified in the input.

