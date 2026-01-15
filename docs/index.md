---
layout: splash
title: Welcome to Phoenix
permalink: /
hidden: true
header:
  overlay_color: "#5e616c"
  overlay_image: /assets/images/mm-home-page-feature.jpg
  actions:
    - label: "<i class='fas fa-download'></i> Get started"
      url: "/docs/"
excerpt: >
  Cluster management designed by system administrators.<br />
  <small><a href="https://github.com/olcf/phoenix">Clone on GitHub</a></small>
feature_row:
  - image_path: /assets/images/feat1.png
    alt: "customizable"
    title: "Super customizable"
    excerpt: "Track arbitrary facts about your hardware. Separate configuration and data. Build your own images. Add plugins to support any hardware."
    url: "/docs/config/basics/"
    btn_class: "btn--primary"
    btn_label: "Learn more"
  - image_path: /assets/images/feat2.png
    alt: "fully responsive"
    title: "Simple"
    excerpt: "Mock up your cluster on your laptop before the hardware arrives. Get up in running in 5 minutes. Use the parts of Phoenix that are useful, ignore the parts you don't need."
    url: "/docs/quick-start/"
    btn_class: "btn--primary"
    btn_label: "Quick Start Tutorial"
  - image_path: /assets/images/feat3.png
    alt: "Scalable"
    title: "Scalable"
    excerpt: "From a small test cluster to a supercomputer with 10,000+ nodes, Phoenix can handle any cluster. Use multiple Phoenix servers for horizontal scale-out."
    url: "/docs/advanced/scaling/"
    btn_class: "btn--primary"
    btn_label: "Scale Phoenix"
---

{% include feature_row %}
