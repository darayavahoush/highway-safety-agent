// Renders a plate like an Indian HSRP: white field, black characters, blue IND strip.
export default function PlateChip({ plate, size = 'md' }) {
  if (!plate) {
    return (
      <div className="plate-wrap">
        <div className={`plate plate--${size} plate--pending`}>
          <span className="plate-text">Reading plate</span>
        </div>
      </div>
    )
  }
  if (plate.readable === false) {
    return (
      <div className="plate-wrap">
        <div className={`plate plate--${size} plate--pending`}>
          <span className="plate-text">No plate read</span>
        </div>
        {size !== 'sm' && <div className="plate-meta"><b>Plate not readable. Check the evidence photo.</b></div>}
      </div>
    )
  }
  const low = plate.confidence < 0.8
  return (
    <div className="plate-wrap">
      <div className={`plate plate--${size}${low ? ' plate--low' : ''}`}>
        <span className="plate-band" aria-hidden="true"><i className="plate-chakra" />IND</span>
        <span className="plate-text">{plate.text}</span>
      </div>
      {size !== 'sm' && (
        <div className="plate-meta">
          <span className="conf" aria-hidden="true"><i style={{ width: `${Math.round(plate.confidence * 100)}%` }} /></span>
          <span>{Math.round(plate.confidence * 100)}% · {plate.votes}/{plate.frames} frames</span>
          {low && <b>Verify manually</b>}
        </div>
      )}
    </div>
  )
}
