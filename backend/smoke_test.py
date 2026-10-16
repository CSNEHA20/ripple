import os
import sys
from falkordb import FalkorDB

host = os.environ.get("FALKORDB_HOST", "localhost")
port = int(os.environ.get("FALKORDB_PORT", 6379))
tenant_id = os.environ.get("TENANT_ID", "smoke")

print(f"Connecting to FalkorDB at {host}:{port} for tenant_{tenant_id}...")
try:
    db = FalkorDB(host=host, port=port)
    g = db.select_graph(f"tenant_{tenant_id}")

    # Create node & edge
    create_cypher = """
    MERGE (a:Service {name:'frontend'})
    MERGE (b:Service {name:'checkout'})
    MERGE (a)-[r:DEPENDS_ON {protocol: 'gRPC', verified: true, source: 'smoke_test'}]->(b)
    RETURN a.name, b.name
    """
    g.query(create_cypher)
    print("Graph node & edge created/merged.")

    # Query it back
    res = g.query("MATCH (a:Service)-[r:DEPENDS_ON]->(b:Service) RETURN a.name, type(r), b.name")
    print(f"Query Result: {res.result_set}")

    assert len(res.result_set) > 0, "No records returned!"
    print("Smoke test PASSED successfully!")
except Exception as e:
    print(f"Smoke test FAILED: {e}", file=sys.stderr)
    sys.exit(1)
