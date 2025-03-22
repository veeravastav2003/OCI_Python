# Orphan Resource Finder for Oracle Cloud Infrastructure (OCI)

## Overview

This Python script identifies orphaned resources in Oracle Cloud Infrastructure (OCI), including:

- **Block Volumes** (Unattached)
- **Boot Volumes** (Unattached)
- **Load Balancers** (With no backends)
- **Public IPs** (Available but not assigned)

The script gathers these details across multiple regions and compartments and saves them in an Excel file.

## Prerequisites

- Python 3.x installed
- Oracle Cloud Infrastructure (OCI) SDK for Python (`oci`)
- Pandas library (`pandas`)
- A properly configured OCI credentials file (`~/.oci/config`)

## Installation

1. Clone this repository:
   ```sh
   git clone https://github.com/your-repo/orphan-resource-finder.git
   cd orphan-resource-finder
   ```
2. Install dependencies:
   ```sh
   pip install oci pandas
   ```

## Usage

Run the script using:

```sh
python orphan_resource_finder.py
```

## How It Works

1. **Load OCI Configuration**: Reads authentication details from `~/.oci/config`.
2. **Identify Orphaned Resources**:
   - Lists all compartments and regions in the tenancy.
   - Checks for unattached block and boot volumes.
   - Identifies load balancers with no backends.
   - Detects reserved and ephemeral public IPs that are not in use.
3. **Export Results**: Stores findings in `Orphan_Resources.xlsx` with separate sheets for each resource type.

## Output

After execution, the script generates an Excel file named `Orphan_Resources.xlsx` containing:

- **Orphan Block Volumes**
- **Orphan Boot Volumes**
- **Orphan Load Balancers**
- **Orphan Public IPs**

## Example Output Format

| Region       | Resource Name   | Resource OCID               | Compartment Name |
| ------------ | --------------- | --------------------------- | ---------------- |
| us-ashburn-1 | Block Volume 1  | ocid1.volume.oc1..xyz       | CompartmentA     |
| us-ashburn-1 | Load Balancer 1 | ocid1.loadbalancer.oc1..xyz | CompartmentB     |

## Notes

- Ensure that the **OCI credentials file is correctly configured** before running the script.
- Modify the script if you need additional filters or resource types.

## Contributions

Feel free to fork and submit pull requests for improvements!

## Author

G Veeravastav

