---
slug: "have-you-already-had-a-chance-to-think-about-why-you-should-consider-using-ubi"
title: "Have You Already Had a Chance to Think About Why You Should Consider Using UBI?"
date: 2023-12-07T10:00:00-04:00
categories:
  - Containers
tags:
  - Red Hat
  - UBI
  - Containers
  - RHEL
  - OpenShift
  - Security
aliases:
  - "/2023/12/07/have-you-already-had-a-chance-to-think-about-why-you-should-consider-using-ubi/"
---

UBI stands for Universal Base Image. It's a type of container-based image that Red Hat has created and maintains. UBI images are derived from Red Hat Enterprise Linux (RHEL) and are designed to be a foundation for building containerized applications. Here's why UBI is significant and why you might consider to use it:

* **Compatibility with RHEL**: UBI is based on RHEL, which means it inherits the reliability, security, and performance of RHEL. This compatibility is crucial for organizations that already rely on RHEL for their enterprise applications.
* **Open and Freely Distributable**: Unlike RHEL, which requires a subscription, UBI can be used freely. This means you can build your container images on UBI and redistribute them without worrying about RHEL licensing, while still benefiting from the stability and security of a RHEL base.
* **Security and Compliance**: UBI images benefit from Red Hat's commitment to security and compliance. They receive regular updates and patches, which is essential for maintaining security in containerized environments.
* **Broad Ecosystem and Support**: Since UBI is based on RHEL, it has broad support from software vendors and the open-source community. This extensive ecosystem ensures compatibility with a wide range of applications and tools.
* **Ease of Certification**: For software vendors, using UBI can simplify the process of certifying their applications for RHEL, as UBI containers can be run on both RHEL and non-RHEL hosts.
* **Container Portability**: Containers built on UBI can run anywhere that supports container workloads, including Red Hat OpenShift, Kubernetes, and even non-Red Hat platforms. This portability is crucial for organizations adopting a hybrid or multi-cloud strategy.
* **Consistency Across Environments**: UBI helps maintain consistency across development, testing, and production environments, reducing the "it works on my machine" problem.
* **Support for Different Architectures**: UBI images are available for multiple architectures, including x86_64, s390x, and others, which is important for organizations with diverse infrastructure needs.

In summary, UBI combines the reliability and security of RHEL with the flexibility and freedom of a container-based image that can be freely shared and redistributed. It's an excellent choice for organizations looking to build containerized applications that are secure, compliant, and compatible with a wide range of environments and platforms. See [more here](https://catalog.redhat.com/software/base-images)
