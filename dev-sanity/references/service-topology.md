# Service Topology Notes

Use this file to think about the local stack in generic terms.

## Minimal Topology Model

Most local environments can be described as four layers:

1. auth or shared platform services
2. backend APIs
3. databases and queues
4. frontends or local clients

## Common Failure Order

When several checks fail, investigate in this order:

1. shared auth/platform service
2. core backend API
3. databases or queues
4. frontend health checks

The first missing dependency usually explains the rest.

## Mode Guidance

Keep real repo names, ports, and health URLs in `modes/config.sh`, not here.
This tracked reference should stay conceptual and reusable.

Not every stack needs every check. If a project has no containers or no health
endpoint, leave that array empty or omit it from the mode file.
