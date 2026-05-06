---
slug: "creating-a-lightweight-jump-host-in-azure-with-sshuttle-no-vpn-required"
title: "Creating a Lightweight Jump Host in Azure with sshuttle (No VPN Required)"
date: 2024-10-04T10:00:00-04:00
categories:
  - Azure
tags:
  - Azure
  - Networking
  - SSH
  - sshuttle
  - Jump Host
aliases:
  - "/2024/10/04/creating-a-lightweight-jump-host-in-azure-with-sshuttle-no-vpn-required/"
---

When working with development or test environments in Azure, a common need is secure access to internal resources without exposing them directly to the internet. While VPN solutions are a robust way to achieve this, they can often be overkill for simple use cases, especially when you just want to access a few VMs or services for testing. A jump host combined with sshuttle offers a simple, VPN-like solution that can be quickly deployed and used to tunnel traffic to your Azure resources—without the overhead of setting up a full VPN.

This guide will walk you through creating a jump host in Azure, automatically generating a new SSH key pair during the VM creation process, and using sshuttle to securely connect to your internal Azure resources.

## Why Use a Jump Host?

A jump host (or bastion host) serves as a gateway into your Azure Virtual Network (VNet) and allows secure access to resources within the network. It's especially useful for developers and IT administrators who need to troubleshoot, test, or access Azure VMs without exposing internal services to the public internet. With the help of sshuttle, you can securely tunnel traffic through the jump host to other VMs and services in the network—acting like a lightweight VPN without complex configuration.

## Prerequisites

Make sure you have the following before starting:

* An Azure subscription.
* Azure CLI installed and configured on your local machine.
* Basic knowledge of SSH and Azure networking.

## Step 1: Create the Jump Host VM in Azure

You can quickly create a jump host VM in Azure using the Azure CLI. Here, we'll leverage the `--generate-ssh-keys` flag, which automatically creates a new SSH key pair if none exists in the default ~/.ssh directory. This eliminates the need for manual SSH key generation, making the setup even easier.

Run the following command:

```bash
az vm create --name jumphost \
    --resource-group rgname \
    --generate-ssh-keys \
    --admin-username user \
    --image "RedHat:RHEL:9_1:9.1.2022112113" \
    --subnet jumpsubnet \
    --public-ip-address jumphost-ip \
    --public-ip-sku Standard \
    --vnet-name jumpvnet
```

### Command Breakdown:

* `--name`: The name of the jump host VM.
* `--resource-group`: The Azure resource group where the VM will be deployed.
* `--generate-ssh-keys`: Automatically generates a new SSH key pair if one doesn't exist. If there's an existing key in ~/.ssh, it will be used instead.
* `--admin-username`: Sets the admin username for SSH connections.
* `--image`: Specifies the base image for the VM (RHEL 9.1 in this example).
* `--subnet`: The subnet in the VNet where the VM will be placed.
* `--public-ip-address`: Allocates a public IP address for the VM.
* `--public-ip-sku`: Sets the IP SKU to "Standard" for better availability.
* `--vnet-name`: The name of the VNet where the subnet is located.

This command creates a jump host named jumphost in the specified resource group, with a public IP address for easy SSH access. The `--generate-ssh-keys` parameter will store the newly generated keys in your ~/.ssh directory:

* **Private key**: ~/.ssh/id_rsa
* **Public key**: ~/.ssh/id_rsa.pub

If you want to specify a custom path for the SSH keys, use the `--ssh-key-values` parameter instead:

```bash
az vm create --name jumphost \
    --resource-group rgname \
    --ssh-key-values ~/.ssh/my_new_key.pub \
    --admin-username user \
    --image "RedHat:RHEL:9_1:9.1.2022112113" \
    --subnet jumpsubnet \
    --public-ip-address jumphost-ip \
    --public-ip-sku Standard \
    --vnet-name jumpvnet
```

## Step 2: Install sshuttle Locally

sshuttle is a powerful tool that creates a VPN-like experience using SSH tunneling. Install `sshuttle` on your local machine with the following commands:

### For macOS:

```bash
brew install sshuttle
```

### For Ubuntu:

```bash
sudo apt-get update && sudo apt-get install sshuttle
```

### For RHEL/CentOS:

```bash
sudo yum install sshuttle
```

## Step 3: Set Up an SSH Tunnel Using sshuttle

Once your jump host is up and running, you can use sshuttle to securely forward traffic to your Azure VNet. The following command will set up an SSH tunnel through the jump host, allowing your local machine to access the internal Azure subnet:

```bash
sshuttle --dns -NHr "user@<jumphost-public-ip>" 10.0.1.0/24 &
```

### Important Note About Running in the Background (&):

If sshuttle is running with elevated permissions (e.g., sudo), using & (which runs the command in the background) might break the password prompt, causing the command to fail. If you need sudo for sshuttle, consider one of the following options:

1. **Run the command without & first** to enter the password, then press CTRL + C to stop the command. After that, run the same command again with &.
2. **Open a new terminal window** and run sshuttle in the background, so you can manage the other terminal independently.

> **Note**: Replace `<jumphost-public-ip>` with the actual public IP address of the VM created in Step 1.

## Step 4: Verify the Tunnel and Connect to Internal Resources

After setting up the SSH tunnel, you should be able to access internal resources in the Azure VNet as if you were connected directly. Test this by pinging an internal IP address or SSH-ing into another VM in the network:

```bash
ping 10.0.1.4
```

Or SSH directly into another VM:

```bash
ssh user@10.0.1.4
```

If you can successfully connect, your SSH tunnel is working, and you have secure access to your internal Azure VNet resources.

## Why Use sshuttle?

sshuttle acts as a lightweight VPN without all the complexities, creating a layer 3 VPN over SSH. It forwards TCP packets and DNS queries through your jump host, providing access to your entire Azure VNet securely and quickly.

## Final Thoughts

Setting up a jump host with sshuttle is an excellent solution for developers, testers, and administrators who want easy access to their Azure resources without the need for complex VPN solutions. With automatic SSH key generation and a few simple commands, you can create a secure gateway into your Azure environment and start accessing resources in minutes.

Give this a try and let me know how it works for you! 😊🔧
