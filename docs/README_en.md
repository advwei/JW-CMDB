
<h3 align="center">Operations Configuration Management Database (Forked from VeOps CMDB)</h3>

<h3 align="center">
  <a href="https://github.com/veops/cmdb">Original Project Link</a>
</h3>

<p align="center">
  <a href="https://github.com/advwei/cmdb_ts/LICENSE"><img src="https://img.shields.io/badge/License-AGPLv3-brightgreen" alt="License: GPLv3"></a>
  <a href="https://github.com/sendya/ant-design-pro-vue"><img src="https://img.shields.io/badge/UI-Ant%20Design%20Pro%20Vue-green" alt="UI"></a>
  <a href="https://github.com/pallets/flask"><img src="https://img.shields.io/badge/API-Flask-bright" alt="API"></a>
</p>
<p align="center">
  <a href="README.md">中文(简体)</a> · English
</p>

## Introduction

This project uses two AI agent tools, Codex and Opencode, and is a secondary development based on the Weiyi CMDB open-source project. No features have been removed, only the following have been added:

- Added Jumpserve asset synchronization
- Added IPAM Agent and synchronization service
- Added Ansible middleware integration
- Added Ansible execution log section
- Added two fixed asset models
- Added reclaimed resource display section
- Added configuration center

## New Notes

### 1. New Directory Structure

```shell
cmdb_ts

│
├── ci_models # Asset Models
├── cmdb-agent # Agent Server Related Code
├── cmdb-ansible-executor # Ansible Intermediate Service
├── tools # Batch IP Synchronization Tool
└── ...
```

### 2. New Features

- **Jumpserve Integration:** Supports pushing recorded assets individually or in batches to the Jumpserve bastion host, automatically deleting corresponding Jumpserve assets during recycling.
- **Ansible Integration:** Supports dynamically generating inventory, customizing execution playbooks, and allowing custom input of additional parameters on the front end.
- **New IPAM Agent:** Supports single full subnet scans (triggered by right-clicking in the UI). The Agent now interacts with the Docker backend via HTTP service.
- **Asset Models:** Added the `vmserver` model to record assets, and the `delserver` model to record recycled assets. Other models still support customization.
- **Ansible Execution Logs:** The front end provides a visual view of the success/failure execution status of Ansible tasks, detailed host information, and standard and error outputs from Ansible execution.
- **Recycle Resources:**
  + Supports one-click batch recycling of resources, with a three-dimensional overview view of recycled resources (CPU, memory, disk).
  + Clicking "recycle" will delete the asset from the `vmserver` model and add it to the `delserver` model, simultaneously deleting the Jumpserve asset and recycling the IP address. + Canceling asset reclamation only rolls back asset data and will not synchronously create new Jumpserve assets and IP addresses. Exercise caution when performing this operation.
- **Configuration Center**: Centralized management, integrating Jumpserve, Ansible, Agent, and asset model IP configuration pages.
  + Jumpserve Configuration: Integration configuration, asset node UUID mapping, asset type mapping
  + Ansible Configuration: Ansible Executor integration configuration, CI field mapping, OS credential mapping
  + Agent Configuration: AgentID, address, port, token
  + Model Configuration: vmserver, delserver model ID configuration

## Technology Stack

+ Backend: Python [3.8-3.11]
+ Data Storage: MySQL, Redis
+ Frontend: Vue.js
+ UI Component Library: Ant Design Vue

## System Overview

<table style="border-collapse: collapse;">
  <tr>
    <td style="padding: 5px;background-color:#fff;">
      <img width="400" src="/docs/readme_images/001.png"/>
    </td>
    <td style="padding: 5px;background-color:#fff;">
      <img width="400" src="/docs/readme_images/002.png"/>
    </td>
  </tr>

  <tr>
    <td style="padding: 5px;background-color:#fff;">
      <img width="400" src="/docs/readme_images/003.png"/>
    </td>
    <td style="padding: 5px;background-color:#fff;">
      <img width="400" src="/docs/readme_images/004.png"/>
    </td>
  </tr>

  <tr>
    <td style="padding: 5px;background-color:#fff;">
      <img width="400" src="/docs/readme_images/005.png"/>
    </td>
    <td style="padding: 5px;background-color:#fff;">
      <img width="400" src="/docs/readme_images/006.png"/>
    </td>
  </tr>

  <tr>
    <td style="padding: 5px;background-color:#fff;">
      <img width="400" src="/docs/readme_images/007.png"/>
    </td>
    <td style="padding: 5px;background-color:#fff;">
      <img width="400" src="/docs/readme_images/008.png"/>
    </td>
  </tr>

</table>

## Quick Start

### 1. Install Dependencies and Pull Code

- Step 1: Install Docker Environment and Docker Compose (v2)

- Step 2: Copy the project code to the /opt directory, `git clone https://github.com/advwei/cmdb_ts.git`

### 2. Build Frontend and Backend Images

+ Docker Quick Build

  - Step 1: Enter the main directory to build the frontend image
    + Backend: The name must match the one in docker-compose.yml
    ```bash
    docker build -f docker/Dockerfile-API -t my-cmdb-api:2.8.6 .
    ```
  - Step 2: Enter the main directory to build the backend image
    + Frontend: The name must match the one in docker-compose.yml
    ```bash
    docker build -f docker/Dockerfile-UI -t my-cmdb-ui:2.8.6 .
    ```

### 3. Agent Deployment

  #### One-Click Installation
  ```bash
  # Enter the Agent folder of the project and execute the one-click installation
  cd /cmdb_ts/cmdb-agent
  sudo bash install.sh
  ```
  #### Other Notes
  - For other installation methods and content introductions, please refer to the [Agent Introduction Document](cmdb-agent/AgentReadMe.md)

### 4. Ansible Intermediate Service Deployment

  #### Prerequisites

- Ansible is already installed on the host machine
- Ansible playbook directory: `/opt/ansible/playbooks/`
- Ansible inventory directory: `/opt/ansible/inventory/`

  #### Deployment service
```bash
  # Navigate to the cmdb-ansible-executor directory and install dependencies.
  cd /opt/cmdb-ansible-executor
  pip install -r requirements.txt

  # edit EXECUTOR_API_KEY
  # Configuration systemd
  cp cmdb-ansible.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable cmdb-ansible
  systemctl start cmdb-ansible

  # check
  curl http://localhost:18081/api/exec/health
```
  #### Other Notes

  - For further information, please refer to the [Ansible Introduction Documentation](cmdb-ansible-executor/AnsibleReadMe.md)
  
### 5. Access

- Enter the project directory `cd /opt/cmdb_ts`
- Start the image, `docker compose up -d`
- Open a browser and access: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Username: admin
- Password: 123456

### 6. Importing Models

#### Importing vmserver and delserver Models

- Import the model files from the ci_models directory into the system [Model Configuration - Import - Select File Upload]
- View the IDs of the vmserver and delserver models, and then enter the corresponding ID values ​​in the model configuration center.
  + (Open your browser with F12, click on the model to view the corresponding interface: /api/v0.1/ci_types/{id} to find the ID)
- Modify the usage attribute in the IP address model to associate it with the asset. Edit Attribute - Drop-down List - Other Model Attributes - vmserver - Asset Name:

|Attribute Name|Alias ​​(Customizable)|Data Type|Drop-down List|
|:------:|:--------------:|:--------:|:--------:|
|usage|Use Asset|Short Text|Other Model Attributes - vmserver - Asset Name|

#### Batch Associate IP Addresses

- To batch associate online IPs and assets, use the script `/tools/ip_import_tools.py`
- Modify the URL, KEY, and SECRET
- Fill in the Excel spreadsheet according to the template and then execute the script

|ip|asset name|
|:------:|:-------:|
|ip|usage|
|10.0.0.0|tomcat_10.0.0.0_Zhang San|

## FQA
Troubleshooting [FQA Documentation](docs/FQA.md)

## Acknowledgements

This project is a secondary development based on the open-source project VeOps CMDB using AI tools by a beginner. Thanks to all contributors to the original project and the VeOps team!

## Related Articles
- <a href="https://github.com/veops/cmdb/tree/master/docs/cmdb_api.md" target="_blank">CMDB Interface Documentation</a>
- <a href="https://github.com/veops/cmdb" target="_blank">Original Project Address</a>