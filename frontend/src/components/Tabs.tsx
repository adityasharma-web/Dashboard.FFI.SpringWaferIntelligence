export type ViewKey = 'individual' | 'stacked' | 'spatial' | 'gangs' | 'export'

export const VIEWS: { key: ViewKey; label: string }[] = [
  { key: 'individual', label: 'Individual wafer' },
  { key: 'stacked', label: 'Stacked wafer' },
  { key: 'spatial', label: 'Spatial signatures' },
  { key: 'gangs', label: 'Gang yield' },
  { key: 'export', label: 'Export' },
]

interface Props {
  active: ViewKey
  onChange: (key: ViewKey) => void
}

export function Tabs({ active, onChange }: Props) {
  return (
    <div className="tab-bar" role="tablist" aria-label="Views">
      {VIEWS.map((v) => (
        <button
          key={v.key}
          type="button"
          role="tab"
          aria-selected={active === v.key}
          onClick={() => onChange(v.key)}
        >
          {v.label}
        </button>
      ))}
    </div>
  )
}
