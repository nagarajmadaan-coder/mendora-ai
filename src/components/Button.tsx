import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Link } from '../lib/router'

/*
  One button style used everywhere, so all buttons look and behave the same.
  - Pass `to="/somewhere"` and it renders a link.
  - Leave out `to` and it renders a real <button>.
*/

type Variant = 'primary' | 'secondary' | 'inverse'
type Size = 'md' | 'lg'

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg font-semibold whitespace-nowrap transition-colors ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-teal-600 ' +
  'disabled:cursor-not-allowed disabled:opacity-60'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-teal-700 text-white shadow-sm hover:bg-teal-800',
  secondary: 'bg-white text-navy-900 ring-1 ring-inset ring-navy-900/15 hover:bg-navy-50',
  inverse: 'bg-white text-navy-900 hover:bg-teal-50 focus-visible:outline-white',
}

const SIZES: Record<Size, string> = {
  md: 'h-11 px-5 text-sm',
  lg: 'h-12 px-6 text-base',
}

interface CommonProps {
  variant?: Variant
  size?: Size
  className?: string
  children: ReactNode
}

type ButtonProps = CommonProps &
  (
    | ({ to: string } & { onClick?: () => void })
    | ({ to?: undefined } & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className' | 'children'>)
  )

export default function Button(props: ButtonProps) {
  const { variant = 'primary', size = 'md', className = '', children } = props
  const classes = `${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`

  if (props.to !== undefined) {
    return (
      <Link to={props.to} onClick={props.onClick} className={classes}>
        {children}
      </Link>
    )
  }

  const { variant: _v, size: _s, className: _c, children: _ch, to: _to, type = 'button', ...rest } = props
  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  )
}
