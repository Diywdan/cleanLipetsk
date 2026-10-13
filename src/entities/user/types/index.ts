export type UserRole = 'INSPECTOR' | 'UK' | 'ADMIN';
// Ведомства из макета; CRM для остальных отдаёт ключ ведомства заглавными (EKOPROM, TRANSPORT…)
export type LipetskDepartment = 'DRT' | 'GZHI' | 'DDHIB' | 'MPLO' | (string & {});

export interface IUser {
  id: string;
  name: string;
  role: UserRole;
  department: LipetskDepartment;
  organizationName?: string; // Заполняется, если роль === 'UK' (например, "УК Левобережная")
}
