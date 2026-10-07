export type UserRole = 'INSPECTOR' | 'UK' | 'ADMIN';
export type LipetskDepartment = 'DRT' | 'GZHI' | 'DDHIB' | 'MPLO';

export interface IUser {
  id: string;
  name: string;
  role: UserRole;
  department: LipetskDepartment;
  organizationName?: string; // Заполняется, если роль === 'UK' (например, "УК Левобережная")
}
