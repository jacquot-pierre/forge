# Gemini Code Assistant Documentation for Ansible Forge

This document provides a comprehensive overview of the Ansible Forge project, designed to help developers and system administrators understand, use, and extend the automation capabilities of this repository.

## Overview

This Ansible project is designed to provision and configure a complete server infrastructure, leveraging Proxmox for virtualization. It automates the setup of various services, including DNS with dnsmasq, load balancing with HAProxy, a PKI infrastructure for certificate management, and a custom media server application called "Machikiflix".

The project is structured to be highly modular, using Ansible roles to separate concerns and make the automation reusable and easy to maintain. It also makes extensive use of `ansible-vault` to securely manage secrets and sensitive data.

## Getting Started

### Prerequisites

- **Python & Poetry**: This project uses Poetry for dependency management. Ensure you have a compatible Python version and `pipx` to install Poetry.
- **Ansible**: Ansible is the core of this project. It will be installed as a dependency by Poetry.
- **Ansible Vault**: You will need to have your vault password files set up in `~/.ansible_vault_credentials/`.

### Installation

1.  **Install Poetry**:
    ```bash
    pipx install --python python3.13 poetry
    ```

2.  **Install dependencies**:
    ```bash
    poetry install
    ```

3.  **Install Ansible collections**:
    ```bash
    poetry run ansible-galaxy collection install community.general
    ```

### Configuration

Secrets are managed using `ansible-vault`. The project is configured to use multiple vault identities. Make sure you have the corresponding password files in place. The identities are:
- `pki`
- `proxmox`
- `machikiflix`

The password files should be located at `~/.ansible_vault_credentials/.ansible_vault_<identity_name>.pass`.

### Running Playbooks

To run a playbook, use the `ansible-playbook` command through `poetry run`. For example, to run the `machikiflix.yml` playbook:

```bash
poetry run ansible-playbook machikiflix.yml
```

## Project Structure

The project is organized as follows:

-   `inventories/`: Contains the inventory files. It uses the Proxmox dynamic inventory plugin to fetch hosts.
-   `roles/`: Contains all the Ansible roles, which are the main components of this automation.
-   `*.yml`: Playbook files in the root directory that define the automation tasks.
-   `ansible.cfg`: The main Ansible configuration file.
-   `pyproject.toml` & `poetry.lock`: Python project and dependency files.

## Roles

Here is a description of the available roles:

-   **common**: Base configuration applied to all servers.
-   **dnsmasq**: Installs and configures dnsmasq as a DNS and DHCP server.
-   **docker**: Installs Docker and Docker Compose.
-   **haproxy**: Sets up HAProxy as a load balancer and reverse proxy. It includes automated certificate renewal.
-   **machikiflix**: Deploys the "Machikiflix" application stack, which includes:
    -   Traefik as a reverse proxy.
    -   Servarr applications (Sonarr, Radarr, etc.).
    -   A torrent client.
    -   A media server.
-   **pki**: Manages a Public Key Infrastructure (PKI) using `step-ca` to issue TLS certificates.
-   **updateca**: A role to update the CA certificates on the managed nodes.

## Playbooks

The main playbooks are:

-   **ca_init.yml**: Initializes the Certificate Authority.
-   **dnsmasq.yml**: Deploys the dnsmasq service.
-   **haproxy.yml**: Deploys and configures HAProxy.
-   **machikiflix.yml**: Deploys the full Machikiflix stack.
-   **pki.yml**: Manages the PKI.

## Inventory

The inventory is dynamic and sourced from a Proxmox server. The configuration is located in `inventories/`. There are separate inventory files for LXC containers and QEMU virtual machines.

To list the inventory, you can run:
```bash
poetry run ansible-inventory -i inventories/inventory_lxc.proxmox.yaml --graph
```

## Secrets Management

Secrets are encrypted using `ansible-vault`. The project uses multiple vault identities to separate secrets for different components.

To edit a vaulted file, use a command like this:
```bash
poetry run ansible-vault edit inventories/group_vars/all/proxmox.yaml
```
