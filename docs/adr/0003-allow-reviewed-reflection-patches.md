# Allow Reviewed Reflection Patches

NAQSHA v1 will include an active-by-default **Reflection Loop** that may generate code changes as isolated **Reflection Patches** after the **Reliability Gate** passes. Those patches cannot hotpatch the active runtime or merge automatically; human approval is required because code-generating reflection is valuable for improvement but risky if prompt injection, memory poisoning, or overfitted replay tests can expand runtime agency without review.
