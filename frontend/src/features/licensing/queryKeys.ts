import type { AdminLicenseFilters } from './types'

export const licensingKeys = {
  all: ['licensing'] as const,
  organization: () => [...licensingKeys.all, 'organization'] as const,
  summary: () => [...licensingKeys.organization(), 'summary'] as const,
  licenses: () => [...licensingKeys.organization(), 'licenses'] as const,
  license: (licenseNumber: string) => [...licensingKeys.licenses(), licenseNumber] as const,
  team: () => [...licensingKeys.organization(), 'team'] as const,
  admin: () => [...licensingKeys.all, 'admin'] as const,
  licenseProducts: () => [...licensingKeys.admin(), 'license-products'] as const,
  adminOrganizations: (filters: AdminLicenseFilters = {}) => [...licensingKeys.admin(), 'organizations', filters] as const,
  adminOrganization: (organizationId: number) => [...licensingKeys.admin(), 'organization', organizationId] as const,
  adminHistory: (organizationId: number, page = 1) => [...licensingKeys.adminOrganization(organizationId), 'history', page] as const,
  adminNotifications: (organizationId: number, page = 1) => [...licensingKeys.adminOrganization(organizationId), 'notifications', page] as const,
}
