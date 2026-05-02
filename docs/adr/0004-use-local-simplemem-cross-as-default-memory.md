# Use Local SimpleMem-Cross as Default Memory

NAQSHA will define a **Memory Port** in the **Core Runtime** and ship a local **SimpleMem-Cross Adapter** as the default v1 memory implementation. This keeps lifelong memory first-class while avoiding a hard dependency on the hosted SimpleMem MCP service, network availability, external auth, or third-party deployment posture; the trade-off is that NAQSHA must own a clean adapter boundary around SimpleMem-Cross lifecycle events.
