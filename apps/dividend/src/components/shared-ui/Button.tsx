/**
 * Button 组件
 * 复制自 packages/shared-ui/src/Button.tsx
 * 试点：apps/dividend 拆离 monorepo
 */
import { ButtonHTMLAttributes, forwardRef } from 'react';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = '', variant = 'primary', size = 'md', children, ...props }, ref) => {
    const baseStyles = 'inline-flex items-center justify-center rounded-md font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

    const variantStyles = {
      primary: 'bg-accent text-white hover:bg-accent-hover focus:ring-accent',
      secondary: 'bg-paper-card text-ink border border-rule hover:bg-paper-tint focus:ring-info',
      ghost: 'hover:bg-paper-deep text-ink focus:ring-info',
      danger: 'bg-down text-white hover:bg-red-700 focus:ring-down',
    };

    const sizeStyles = {
      sm: 'px-2 py-1 text-xs',
      md: 'px-4 py-2 text-sm',
      lg: 'px-6 py-3 text-base',
    };

    return (
      <button
        ref={ref}
        className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
        {...props}
      >
        {children}
      </button>
    );
  }
);

Button.displayName = 'Button';
