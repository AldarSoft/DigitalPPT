import type { AdminLicenseFilters } from './types'

export const licensingKeys = {
  all: ['licensing'] as const,
  organization: () => [...licensingKeys.all, 'organization'] as const,
  workspaces: () => [...licensingKeys.organization(), 'workspaces'] as const,
  summary: (organizationId?: number | null) => [...licensingKeys.organization(), organizationId ?? 'default', 'summary'] as const,
  licenses: (organizationId?: number | null) => [...licensingKeys.organization(), organizationId ?? 'default', 'licenses'] as const,
  license: (licenseNumber: string, organizationId?: number | null) => [...licensingKeys.licenses(organizationId), licenseNumber] as const,
  team: (organizationId?: number | null) => [...licensingKeys.organization(), organizationId ?? 'default', 'team'] as const,
  admin: () => [...licensingKeys.all, 'admin'] as const,
  licenseProducts: () => [...licensingKeys.admin(), 'license-products'] as const,
  adminOrganizations: (filters: AdminLicenseFilters = {}) => [...licensingKeys.admin(), 'organizations', filters] as const,
  adminOrganization: (organizationId: number) => [...licensingKeys.admin(), 'organization', organizationId] as const,
  adminHistory: (organizationId: number, page = 1) => [...licensingKeys.adminOrganization(organizationId), 'history', page] as const,
  adminNotifications: (organizationId: number, page = 1) => [...licensingKeys.adminOrganization(organizationId), 'notifications', page] as const,
}
