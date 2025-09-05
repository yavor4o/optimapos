# Metronic Theme Guide

## Important Theme Information

**Theme:** Metronic 9 with Tailwind CSS 4
**Framework:** NOT Bootstrap - uses Metronic's own component classes

## Key Class Prefixes

### Buttons
- `kt-btn` - Base button class
- `kt-btn-primary` - Primary button
- `kt-btn-secondary` - Secondary button  
- `kt-btn-destructive` - Destructive/danger button
- `kt-btn-outline` - Outline variant
- `kt-btn-sm` - Small size

### Cards  
- `kt-card` - Base card class
- `kt-card-content` - Card content wrapper

### Tables
- `kt-table` - Base table class (DO NOT change this)
- Use existing kt-table structure, don't replace with custom table styling

### Badges
- `kt-badge` - Base badge class
- `kt-badge-success` - Success variant
- `kt-badge-warning` - Warning variant  
- `kt-badge-danger` - Danger variant
- `kt-badge-sm` - Small size

### Forms
- `kt-input` - Input field
- `kt-select` - Select dropdown
- `kt-input-sm` - Small input size

### Layout
- `kt-container-fixed` - Fixed width container

## CSS Framework Notes
- Uses Tailwind CSS 4 for utilities (spacing, colors, flexbox, etc.)
- Metronic provides the component classes (kt-*)  
- Combine both: `kt-btn kt-btn-primary px-4 py-2` (Metronic component + Tailwind utilities)

## DO NOT
- Replace kt-table with custom table styling
- Use Bootstrap classes
- Create custom component classes when Metronic equivalents exist

## DO
- Use kt-* classes for components  
- Use Tailwind utilities for spacing, colors, layout
- Keep existing component structure intact