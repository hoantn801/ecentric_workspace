"""PM v2 service API package.

Whitelisted services (module paths the portal pages will call):
  ecentric_workspace.pm.api.projects.list   / .projects.get
  ecentric_workspace.pm.api.tasks.list      / .tasks.get
  ecentric_workspace.pm.api.tasks.create    / .tasks.set_status / .tasks.assign
  ecentric_workspace.pm.api.dashboard.summary

Ticket: PM1-T00 (scaffold). Stubs only - no data access, no production wiring.
"""
