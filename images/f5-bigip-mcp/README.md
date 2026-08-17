# f5-bigip-mcp

Read-only iControl REST tools for the lab F5 at `172.16.10.10`.
Build on Viper, then `ctr images import` into k3s-viper as `f5-bigip-mcp:dev`.
Creds from Vault `secret/platform/f5-bigip` (host, username, password). Never bake them in.
