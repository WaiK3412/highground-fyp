import { splitItems } from '../../appeals'

/** An appeal's items as a list, so a donor can see at a glance what is still needed. */
export default function ItemList({ items, className = 'text-sm' }) {
  return (
    <ul className={className} style={{ margin: 0, paddingLeft: '1.2rem' }}>
      {splitItems(items).map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}
    </ul>
  )
}
