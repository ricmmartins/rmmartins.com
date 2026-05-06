---
slug: "what-to-consider-when-using-azure-ad-as-idp"
title: "What to Consider When Using Azure AD as IDP"
date: 2024-05-24T10:00:00-04:00
categories:
  - Azure
  - OpenShift
tags:
  - Azure
  - ARO
  - Azure AD
  - Identity Provider
  - OpenShift
aliases:
  - "/2024/05/24/what-to-consider-when-using-azure-ad-as-idp/"
---

*This article was originally published at [What to consider when using Azure AD as IDP? | Red Hat Cloud Experts](https://cloud.redhat.com/experts/idp/considerations-aad-ipd/)*

In this guide, we will discuss key considerations when using Azure Active Directory (AAD) as the Identity Provider (IDP) for your ARO or ROSA cluster. Below are some helpful references:

* [Configure ARO to Use Azure AD](https://cloud.redhat.com/experts/idp/azuread-aro/)
* [Configuring IDP for ROSA, OSD, and ARO](https://cloud.redhat.com/experts/idp/azuread/)

## Default Access for All Users in Azure Active Directory

Once you set up AAD as the IDP for your cluster, it's important to note that by default, all users in your Azure Active Directory instance will have access to the cluster. They can log in using their AAD credentials through the OpenShift Web Console endpoint:

![](/wp-content/uploads/2026/02/image-1024x277.png)

However, for security purposes, it's recommended to restrict access and only allow specific users who are assigned to access the cluster.

## Restricting Access

To implement access restrictions, follow these steps:

1. Log in to the Azure Portal and navigate to your AAD instance.

2. Under Enterprise applications, select the application created for the ARO IDP configuration.

![](/wp-content/uploads/2026/02/image-1-1024x487.png)

3. In the selected Enterprise application, go to Properties and switch the **"Assignment required?"** option to **YES**.

![](/wp-content/uploads/2026/02/image-2-1024x624.png)

4. If you attempt to log in at this point, you will receive a denial error:

Enter your username:

![](/wp-content/uploads/2026/02/image-3.png)

Enter your password:

![](/wp-content/uploads/2026/02/image-4.png)

The error message indicates that only users specifically granted access to the application are allowed:

![](/wp-content/uploads/2026/02/image-5-1024x623.png)

5. To allow access, go to Users and groups in the main blade, click **+ Add user/group**, and add the desired users/groups who should have access to the ARO cluster.

![](/wp-content/uploads/2026/02/image-6-1024x495.png)

Search for the desired user/group and click **Select**.

![](/wp-content/uploads/2026/02/image-7-1003x1024.png)

Verify that the user has been assigned:

![](/wp-content/uploads/2026/02/image-8-1024x421.png)

6. You should now be able to log in with the specified user/group to your cluster:

Enter your username:

![](/wp-content/uploads/2026/02/image-9.png)

Enter your password:

![](/wp-content/uploads/2026/02/image-10.png)

You will then be logged in:

![](/wp-content/uploads/2026/02/image-11-1024x450.png)

## Approval Workflow

If you receive a message like the one below, it means that your AAD has the [admin consent workflow](https://learn.microsoft.com/en-us/azure/active-directory/manage-apps/configure-admin-consent-workflow) enabled:

![](/wp-content/uploads/2026/02/image-12.png)

In this case, you will need to request and wait for approval from your AAD domain admin. To request access, fill out the request form:

![](/wp-content/uploads/2026/02/image-13.png)

And wait for approval:

![](/wp-content/uploads/2026/02/image-14.png)

## Self-Approval Process

If you have administrative privileges, you can self-approve the request by following these steps:

> Please note that these steps are based on the official guidance from Microsoft, which is [available here.](https://learn.microsoft.com/en-us/azure/active-directory/manage-apps/review-admin-consent-requests)

1. Go to your Azure Active Directory Tenant > Enterprise Applications > Admin Consent Requests > All (Preview):

![](/wp-content/uploads/2026/02/image-15-1024x915.png)

2. Select the application (openshift, in this case) and click **Review permissions and consent**:

![](/wp-content/uploads/2026/02/image-16-1024x319.png)

3. A new window will open, prompting you to log in with credentials of an admin with permissions:

![](/wp-content/uploads/2026/02/image-17-1024x588.png)

4. Click **Accept** to consent to the permission:

![](/wp-content/uploads/2026/02/image-18-1024x600.png)

You will then see that the request was approved:

![](/wp-content/uploads/2026/02/image-19-1024x264.png)

Now you will be able to log in through the AAD option:

![](/wp-content/uploads/2026/02/image-20-1024x277.png)

Enter your username:

![](/wp-content/uploads/2026/02/image-22.png)

Enter your password:

![](/wp-content/uploads/2026/02/image-23.png)

It worked!

![](/wp-content/uploads/2026/02/image-24-1024x450.png)

As a best practice, we recommend removing the kubeadmin user after setting up an identity provider. You can find instructions on how to do this [here](https://docs.openshift.com/container-platform/4.13/authentication/remove-kubeadmin.html).

## Using the Group Sync Operator

Integrating groups from external identity providers with OpenShift, such as synchronizing groups from AAD, can be a valuable feature to enhance your system's functionality. To accomplish this, you can leverage the usage of the [Group Sync Operator](https://github.com/redhat-cop/group-sync-operator).

We have published a comprehensive how-to guide that walks you through the process, [accessible here](https://cloud.redhat.com/experts/idp/az-ad-grp-sync). By following these instructions, you'll be able to seamlessly synchronize AAD groups into your OpenShift environment, optimizing your workflow and streamlining access management.
