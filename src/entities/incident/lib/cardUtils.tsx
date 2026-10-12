import React from 'react';
import type { IncidentStatus } from '../types';
import { StatusTag } from '../ui/StatusTag';

export const getStatusBadge = (currentStatus: IncidentStatus): React.ReactNode => (
  <StatusTag status={currentStatus} />
);
