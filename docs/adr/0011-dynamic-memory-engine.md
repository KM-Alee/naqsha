# 0011 Dynamic Memory Engine with Autonomous Schema Evolution

In NAQSHA V2, agents are no longer restricted to a static session memory schema. We introduce a **Dynamic Memory Engine** backed by SQLite. Agents will have access to a Memory Schema Tool, allowing them to autonomously execute DDL to create new tables or restructure their memory as they evolve. Additionally, when initializing a workspace, developers can opt-in to vector embeddings (via `sqlite-vec`), giving the agent native semantic search capabilities within its isolated database.
