import { endpoints } from '../endpoints'
import { api } from '../http'
import type { Department, DepartmentMember, Person, TenantPersonBinding } from '../types'

export interface PersonInput {
  name: string
  mobile?: string | null
  email?: string | null
  status?: string
}

export interface DepartmentInput {
  code: string
  name: string
}

export interface TenantPersonInput {
  person_id: string
  employee_no?: string | null
  external_user_id?: string | null
  display_name?: string | null
}

export const orgApi = {
  persons: (limit = 200) => api.get<Person[]>(endpoints.persons(limit)),

  createPerson: (input: PersonInput) => api.post<Person>(endpoints.persons(1).split('?')[0], input),

  updatePerson: (id: string, input: Partial<PersonInput>) =>
    api.patch<Person>(endpoints.person(id), input),

  departments: (limit = 200) => api.get<Department[]>(endpoints.departments(limit)),

  createDepartment: (input: DepartmentInput) =>
    api.post<Department>(endpoints.departments(1).split('?')[0], input),

  departmentMembers: (id: string) => api.get<DepartmentMember[]>(endpoints.departmentMembers(id)),

  addDepartmentMember: (id: string, personId: string) =>
    api.post<DepartmentMember>(endpoints.departmentMembers(id), { person_id: personId }),

  disableDepartmentMember: (id: string, personId: string) =>
    api.post<unknown>(endpoints.disableDepartmentMember(id, personId)),

  tenantPersons: (tenantId: string) =>
    api.get<TenantPersonBinding[]>(endpoints.tenantPersons(tenantId)),

  bindTenantPerson: (tenantId: string, input: TenantPersonInput) =>
    api.post<TenantPersonBinding>(endpoints.bindTenantPerson(tenantId), input),

  updateTenantPersonBinding: (tenantId: string, personId: string, status: string) =>
    api.patch<TenantPersonBinding>(endpoints.tenantPersonBinding(tenantId, personId), { status }),
}
