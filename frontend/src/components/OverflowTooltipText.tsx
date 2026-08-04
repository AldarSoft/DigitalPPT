import { useLayoutEffect, useRef, useState } from 'react'

type TextElement = 'span' | 'strong' | 'small'

export function OverflowTooltipText({
  as = 'span',
  text,
  className,
}: {
  as?: TextElement
  text: string
  className?: string
}) {
  const ref = useRef<HTMLElement>(null)
  const [isClipped, setIsClipped] = useState(false)

  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return

    const measure = () => {
      setIsClipped(
        element.scrollWidth > element.clientWidth ||
        element.scrollHeight > element.clientHeight,
      )
    }

    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [text])

  const shared = {
    className,
    title: isClipped ? text : undefined,
    children: text,
  }

  if (as === 'strong') return <strong ref={ref} {...shared} />
  if (as === 'small') return <small ref={ref} {...shared} />
  return <span ref={ref} {...shared} />
}
