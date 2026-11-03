const LINKABLE_ISSUES = new Set([
  'control_kind', 'control_form', 'control_body', 'controlled_organization', 'control_object',
  'approver', 'planned_start_at', 'planned_end_at', 'bases', 'decision.items',
  'control_object.address',
  'unit.email',
  'inspectors', 'requisites', 'requisites.inn', 'requisites.legal_address',
  'assignment_date', 'actual_start_at', 'actual_end_at', 'actions',
  'act_composed_at', 'violations', 'prescription',
  'decision', 'decision.decision_date',
]);

export const isDocumentServiceIssueLinkable = (field: string) => LINKABLE_ISSUES.has(field)
  || /^action\.\d+\.(started_at|ended_at|place)$/.test(field)
  || /^violation\.\d+\.provisions$/.test(field);
