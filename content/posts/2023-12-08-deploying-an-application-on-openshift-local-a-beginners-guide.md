---
slug: "deploying-an-application-on-openshift-local-a-beginners-guide"
title: "Deploying an Application on OpenShift Local: A Beginner's Guide"
date: 2023-12-08T10:00:00-04:00
categories:
  - OpenShift
tags:
  - OpenShift
  - Kubernetes
  - Containers
  - Red Hat
  - Local Development
aliases:
  - "/2023/12/08/deploying-an-application-on-openshift-local-a-beginners-guide/"
---

## Introduction

OpenShift, developed by Red Hat, extends Kubernetes to provide a more robust platform for deploying and managing containerized applications in a complete application platform. It integrates the core features of Kubernetes with additional tools and services to enhance developer productivity and operational efficiency. This guide aims to introduce beginners to deploying applications on OpenShift Local, a streamlined method to run OpenShift clusters locally for development and testing.

Using a local OpenShift environment, offers several benefits, especially for developers who are new to OpenShift or Kubernetes:

* **Safe Learning Environment**: It allows experimenting without the risk of affecting a production environment. This is crucial for beginners who are learning the ropes of container orchestration and application deployment.
* **Cost-Effective**: There's no need for cloud resources, making it an economical solution for testing and development purposes.
* **Convenience**: Developers can easily test and debug their applications locally, which streamlines the development process.

Several methods for setting up OpenShift locally include:

1. **[OpenShift Local](https://developers.redhat.com/products/openshift-local/overview)**: This is the new name for CodeReady Containers. OpenShift Local is an official Red Hat solution to run OpenShift 4.x locally. It provides a straightforward way to create a single-node OpenShift 4 cluster.
2. **[MiniShift](https://github.com/minishift/minishift)**: An older tool compared to CodeReady Containers. MiniShift was commonly used for running a single-node OpenShift cluster. It runs on top of a virtual machine and is suitable for development and testing purposes. MiniShift supports OpenShift 3.x versions.
3. **[OKD](https://www.okd.io/)**: OKD is the Community Distribution of Kubernetes that powers Red Hat OpenShift. It offers more flexibility and can be used to set up a more extensive development environment than CodeReady Containers or MiniShift. However, setting up an OKD cluster is generally more complex.
4. **Containerized Development Environments**: Some developers choose to use containerized development environments that mimic OpenShift's behavior. Tools like [Docker](https://www.docker.com/) and [Podman](https://podman.io/) can be used to run OpenShift components in containers. This approach requires more manual setup and configuration.

Each method has its benefits, depending on your project needs and system capabilities. In this post I'll cover the usage of OpenShift Local.

## Step-by-Step Deployment on Local OpenShift

To get started with OpenShift Local, download the crc tool from the [Red Hat Console](https://console.redhat.com/openshift/create/local). If you don't have a Red Hat account, you can create one for free with the [Red Hat Developer program](https://developers.redhat.com/about).

### Step 1: Start Your Local OpenShift Cluster

* Download OpenShift Local: Visit the [OpenShift Local download page](https://cloud.redhat.com/openshift/install/crc/installer-provisioned) and download the version for your OS.
* Install CodeReady Containers:
  * Extract the downloaded file.
  * Run the setup command: `crc setup`

* Start the OpenShift Cluster:
  * Initialize the cluster: `crc start`
  * This process may take several minutes.

* Access OpenShift Console:
  * Retrieve the console URL and login details: `crc console --credentials`

![](https://github.com/ricmmartins/rmmartinscom/raw/master/assets/images/openshiftlocal.png)

### Step 2: Install the OpenShift CLI (oc)

If you haven't already installed the OpenShift CLI, download and install it from the [Red Hat Console](https://console.redhat.com/openshift/downloads#tool-oc).

### Step 3: Authenticate to OpenShift

Authenticate to your OpenShift cluster using the oc CLI, this will allow you to execute deployment commands:

```bash
oc login -u developer -p developer
```

### Step 4: Create a New Project

A project in OpenShift is akin to a Kubernetes namespace but with additional management features. It's a logical grouping that helps in resource organization, isolation, and multi-tenancy.

```bash
oc new-project my-php-project
```

### Step 5: Deploy the Application

In this guide, we'll deploy the [ricmmartins/aro-demo-dryrun](https://github.com/ricmmartins/aro-demo-dryrun) PHP application.

```bash
oc new-app https://github.com/ricmmartins/aro-demo-dryrun.git
```

### Step 6: Monitor the Deployment

To monitor the deployment process, use:

```bash
oc status
```

### Step 7: Expose Your Application

In OpenShift, a 'route' is a powerful concept that exposes a service to an external host name.

```bash
oc expose svc/aro-demo-dryrun
```

### Step 8: Access the Application

Use `oc get route` to find the URL of your application:

```bash
oc get route/aro-demo-dryrun
```

Visit the URL in your browser to view your PHP application.

![](https://github.com/ricmmartins/rmmartinscom/raw/master/assets/images/phpapp.png)

### Conclusion

Deploying an application on OpenShift Local is a beginner-friendly way to delve into the world of Kubernetes and container orchestration. This hands-on experience lays a solid foundation for more advanced OpenShift concepts and practices. As developers become more comfortable with OpenShift, they can explore its full potential in cloud environments, scaling, and managing complex, containerized applications.
