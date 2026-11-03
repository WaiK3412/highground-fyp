import { Icon, PATHS } from '../../icons'

const MAX_PHOTOS = 5

export default function StepPhotos({ data, set }) {
  function addFiles(event) {
    const chosen = Array.from(event.target.files || [])
    set({ photos: [...data.photos, ...chosen].slice(0, MAX_PHOTOS) })
    // Clear the input so picking the same file twice still fires a change.
    event.target.value = ''
  }

  return (
    <div className="card mb-24">
      <h2 className="h3 mb-4">Photos of the damage</h2>
      <p className="text-sm text-muted mb-24">
        Optional, but photos help an officer verify your case faster. Up to {MAX_PHOTOS}.
      </p>

      <div className="stack gap-24">
        <div className="field">
          <label className="btn btn--secondary request-photo-picker" style={{ cursor: 'pointer', alignSelf: 'flex-start' }}>
            <Icon path={PATHS.camera} />
            Choose photos
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={addFiles}
              className="visually-hidden"
              disabled={data.photos.length >= MAX_PHOTOS}
            />
          </label>
          <span className="help">
            {data.photos.length} of {MAX_PHOTOS} selected. JPEG, PNG or WebP, up to 5 MB each.
          </span>
        </div>

        {data.photos.length > 0 && (
          <div className="row" style={{ flexWrap: 'wrap', gap: '1.2rem' }}>
            {data.photos.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                style={{
                  width: '14rem',
                  border: '1px solid var(--grey-200)',
                  borderRadius: 'var(--radius-md)',
                  overflow: 'hidden',
                }}
              >
                <img
                  src={URL.createObjectURL(file)}
                  alt={file.name}
                  style={{ width: '100%', height: '10rem', objectFit: 'cover', display: 'block' }}
                />
                <button
                  className="btn btn--ghost btn--sm btn--full"
                  onClick={() => set({ photos: data.photos.filter((_, i) => i !== index) })}
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
