# Use QAOA Trace Events and NAP Actions

NAQSHA will persist agent runs as **QAOA Trace** events and require model decisions to use strict **NAP Action** envelopes. A **NAP Action** may contain multiple tool calls, but the **Tool Scheduler** only runs them in parallel when they are read-only, independent, and policy-approved; this keeps replay, evaluation, and debugging independent from provider-specific chat formats while avoiding storage of private chain-of-thought. The trade-off is that NAQSHA owns a small protocol surface instead of relying only on provider-native messages.
