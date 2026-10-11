import React from 'react'
import { FileHeart } from 'lucide-react'
import { PageHeader, EmptyState } from '../../components/ui.jsx'
import RecordViewer from '../../components/RecordViewer.jsx'
import { isEmptyRecord } from '../../lib/records.js'
import { usePatient } from './PatientLayout.jsx'

export default function PatientRecords() {
  const { record } = usePatient()
  return (
    <>
      <PageHeader
        title="Health records"
        subtitle={`Record ${record.patient_ref}. Conditions, medications, lab results and visits.`}
      />
      {isEmptyRecord(record) ? (
        <div className="card">
          <EmptyState icon={FileHeart} title="Nothing on file yet">
            Once conditions, prescriptions, lab results or visits are added to your record, they’re listed here.
          </EmptyState>
        </div>
      ) : (
        <RecordViewer record={record} />
      )}
    </>
  )
}
