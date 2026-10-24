// Shared "nothing here" and "loading" blocks, so every page words and styles them the same way.
import { WifiOff } from 'lucide-react'

export function EmptyState({ icon: Icon, title, children, tight = false }) {
  return (
    <div className={`empty${tight ? ' empty--tight' : ''}`}>
      {Icon && <Icon size={28} aria-hidden="true" />}
      <p><b>{title}</b></p>
      {children && <p>{children}</p>}
    </div>
  )
}

// Grey placeholder rows shown while the first data is on its way.
export function SkeletonRows({ count = 3, label = 'Loading' }) {
  return (
    <div className="skel-list" role="status" aria-busy="true">
      <span className="sr-only">{label}…</span>
      {Array.from({ length: count }, (_, n) => (
        <div className="skel-row" key={n} aria-hidden="true">
          <span className="skel skel--icon" />
          <span className="skel-lines">
            <span className="skel skel--line" />
            <span className="skel skel--line skel--short" />
          </span>
        </div>
      ))}
    </div>
  )
}

export function OfflineState({ what = 'incidents' }) {
  return (
    <EmptyState icon={WifiOff} title="Can’t reach the tracker">
      The app keeps retrying on its own. Until it reconnects, an empty list does not mean the road is clear. New {what} will appear here once it is back.
    </EmptyState>
  )
}
