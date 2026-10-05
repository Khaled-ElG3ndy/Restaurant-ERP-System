# Implementation Notes - POS Session Type Selector

## Advanced Customization Guide

This document provides detailed information for developers who want to extend or customize the module further.

---

## Architecture Overview

### Component Hierarchy

```
OWL Component System
│
├── SessionTypeModal (Custom Component)
│   ├── Template: session_type_selector.xml
│   ├── Styling: session_type_selector.css
│   └── Props: onSelect, onCancel
│
└── Chrome (Patched Component)
    ├── selectSession() [Intercepted]
    ├── _showOrderTypeModal() [New Method]
    └── Dialog Service Integration
```

### Patch Architecture

```
Original Flow:
User Click (Continue Selling)
    ↓
Chrome.selectSession(session)
    ↓
Open POS

Modified Flow with Patch:
User Click (Continue Selling)
    ↓
Chrome.selectSession(session) [INTERCEPTED]
    ↓
_showOrderTypeModal()
    ↓
[User selects type]
    ↓
sessionStorage.setItem()
    ↓
super.selectSession(session)
    ↓
Open POS
```

---

## Extending the Modal

### Adding More Order Types

**File**: `/static/src/xml/session_type_selector.xml`

1. Add new card in modal-content:
```xml
<div class="order-type-card custom-type-card" 
     t-on-click="() => this.selectOrderType('custom_type')">
    <div class="card-icon-wrapper">
        <i class="fa fa-your-icon card-icon"></i>
    </div>
    <h3 class="card-title">Your Type</h3>
    <p class="card-description">Description here</p>
</div>
```

2. Add styling in `/static/src/css/session_type_selector.css`:
```css
.custom-type-card {
    background: linear-gradient(135deg, #e0e7ff 0%, #e0e7ff 100%);
}

.custom-type-card:hover {
    border-color: #6366f1;
    background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%);
    box-shadow: 0 8px 24px rgba(99, 102, 241, 0.15);
}

.custom-type-card .card-icon {
    color: #6366f1;
}
```

3. Handle the new type in `/static/src/js/session_type_selector.js`:
```javascript
// In patchProductScreen or new method:
if (orderType === "custom_type") {
    // Add custom logic here
}
```

---

## Server-Side Integration

### Storing Order Type in Database

To persist the order type in the database:

**Create `models/pos_order.py`**:
```python
from odoo import models, fields

class PosOrder(models.Model):
    _inherit = 'pos.order'
    
    order_type = fields.Selection([
        ('takeout', 'Takeout (سفري)'),
        ('dine-in', 'Dine-in (محلي)'),
    ], string='Order Type', default='takeout')
```

**Create `models/pos_session.py`**:
```python
from odoo import models, fields

class PosSession(models.Model):
    _inherit = 'pos.session'
    
    default_order_type = fields.Selection([
        ('takeout', 'Takeout'),
        ('dine-in', 'Dine-in'),
    ], string='Default Order Type', default='takeout')
```

**Update `__manifest__.py`**:
```python
'data': [
    # Add any data files
],
'external_dependencies': {
    'python': [],
},
```

---

## Advanced Scenarios

### 1. Different Pricing by Order Type

In `/static/src/js/session_type_selector.js`, patch the Order model:

```javascript
export const patchOrder = () => {
    try {
        const { Order } = require("point_of_sale.Order");
        
        patch(Order.prototype, {
            get_total() {
                const total = super.get_total();
                const orderType = sessionStorage.getItem("pos_session_order_type");
                
                if (orderType === "dine-in") {
                    // Add service charge for dine-in
                    return total * 1.05;
                }
                return total;
            },
        });
    } catch (e) {
        console.warn("Could not patch Order:", e);
    }
};
```

### 2. Auto-Navigate to Floor Screen for Dine-in

```javascript
export const patchChrome = () => {
    const { Chrome } = require("point_of_sale.Chrome");
    
    patch(Chrome.prototype, {
        async selectSession(session) {
            const orderType = await this._showOrderTypeModal();
            sessionStorage.setItem("pos_session_order_type", orderType);
            
            await super.selectSession(session);
            
            // Auto-navigate to floor screen for dine-in
            if (orderType === "dine-in") {
                try {
                    const floorScreen = this.env.services["pos_restaurant.floorscreen"];
                    if (floorScreen) {
                        this.push_screen("FloorScreen");
                    }
                } catch (e) {
                    console.debug("FloorScreen not available");
                }
            }
        },
    });
};
```

### 3. Table Selection for Dine-in

Create additional modal for table selection:

```javascript
export class TableSelectionModal extends Component {
    static template = "pos_session_type_selector.TableSelectionModal";
    static props = {
        tables: Array,
        onSelect: Function,
    };
    
    selectTable(table) {
        sessionStorage.setItem("pos_selected_table", table.id);
        this.props.onSelect(table);
    }
}
```

### 4. Analytics and Reporting

Store order type for reporting:

```python
# In Python model
class PosOrderAnalysis(models.Model):
    _inherit = 'report.point_of_sale.report_saledetails'
    
    def _query(self, date_start, date_stop):
        query = super()._query(date_start, date_stop)
        # Add order_type to query for analysis
        return query
```

---

## JavaScript/OWL Patterns

### Pattern 1: Using Services

```javascript
// In a component or patch
export class MyComponent extends Component {
    setup() {
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.orm = useService("orm");
    }
    
    async performAction() {
        this.notification.add("Action completed");
    }
}
```

### Pattern 2: Async Dialog

```javascript
async _showModal() {
    const dialogService = this.env.services.dialog;
    
    return new Promise((resolve) => {
        const close = dialogService.add(Dialog, {
            body: MyModalComponent,
            bodyProps: {
                onConfirm: (value) => {
                    close();
                    resolve(value);
                },
            },
        });
    });
}
```

### Pattern 3: Patching Methods

```javascript
// Patch existing method
patch(TargetClass.prototype, {
    existingMethod(arg) {
        // Call original
        const result = super.existingMethod(arg);
        
        // Add custom logic
        this.customLogic();
        
        return result;
    },
});
```

---

## Testing the Module

### Manual Testing Checklist

- [ ] Install module in fresh Odoo 17 instance
- [ ] Navigate to POS Dashboard
- [ ] Click "Continue Selling"
- [ ] Modal appears within 500ms
- [ ] Modal is centered on screen
- [ ] Both buttons (سفري, محلي) are clickable
- [ ] Clicking a button opens POS normally
- [ ] Order type is accessible in POS (check console)
- [ ] Responsive design on mobile (test with DevTools)
- [ ] RTL layout is correct (Arabic text alignment)
- [ ] Cancel button works (closes modal without opening POS)
- [ ] Icons display correctly
- [ ] Animations are smooth
- [ ] No console errors

### Unit Testing Example (Jest)

```javascript
describe('SessionTypeModal', () => {
    it('should call onSelect with correct order type', () => {
        const onSelect = jest.fn();
        const wrapper = mount(SessionTypeModal, {
            props: {
                onSelect,
                onCancel: jest.fn(),
            },
        });
        
        wrapper.find('.takeout-card').trigger('click');
        expect(onSelect).toHaveBeenCalledWith('takeout');
    });
});
```

---

## Debugging Tips

### 1. Console Logging

```javascript
// Add to session_type_selector.js
console.log("📦 Module loaded");
console.log("🔌 Patches applied");
console.log("✅ Initialization complete");

// Debug order type
console.log("📝 Order Type:", sessionStorage.getItem("pos_session_order_type"));
```

### 2. Browser DevTools

In browser console:
```javascript
// Check if module loaded
window.pos_session_type_selector // Should exist

// Check order type
sessionStorage.getItem("pos_session_order_type")

// Check Chrome component
console.log(require("point_of_sale.Chrome"))

// Check dialog service
console.log(this.env.services.dialog)
```

### 3. Network Tab

- Check that `session_type_selector.js` is loaded
- Check CSS file is loaded
- Check XML template is loaded
- Look for 404 errors

### 4. Application Tab

- Check sessionStorage for "pos_session_order_type" key
- Verify value is "takeout" or "dine-in"

---

## Performance Optimization

### 1. Lazy Loading
```javascript
// Load module only when needed
const SessionTypeModal = lazy(() => 
    import('./session_type_selector')
);
```

### 2. Memoization
```javascript
const getOrderType = (() => {
    let cached = null;
    return () => {
        if (!cached) {
            cached = sessionStorage.getItem("pos_session_order_type");
        }
        return cached;
    };
})();
```

### 3. CSS Optimization
- Use `will-change` for animations
- Minimize repaints with `transform` instead of `top/left`
- Use `gpu` acceleration for smooth animations

---

## CSS Customization Deep Dive

### Animation Timings

Edit `/static/src/css/session_type_selector.css`:

```css
/* Fade in speed */
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

.pos-session-type-modal-overlay {
    animation: fadeIn 0.3s ease-in-out;  /* Change 0.3s */
}

/* Slide up speed */
@keyframes slideUp {
    from {
        opacity: 0;
        transform: translateY(30px) scale(0.95);
    }
    to {
        opacity: 1;
        transform: translateY(0) scale(1);
    }
}

.pos-session-type-modal {
    animation: slideUp 0.4s ease-out;  /* Change 0.4s */
}
```

### Color Customization

```css
/* Header gradient */
.modal-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    /* Change to your brand colors */
    background: linear-gradient(135deg, #YOUR_COLOR_1 0%, #YOUR_COLOR_2 100%);
}

/* Card hover colors */
.takeout-card:hover {
    border-color: #667eea;  /* Change this */
}

.dine-in-card:hover {
    border-color: #10b981;  /* Change this */
}
```

### Responsive Breakpoints

Add custom breakpoints:

```css
@media (max-width: 800px) {
    /* Tablet size */
    .modal-content {
        grid-template-columns: 1fr;
    }
}

@media (max-width: 400px) {
    /* Small phone */
    .modal-title {
        font-size: 20px;
    }
}
```

---

## Module Dependencies

### Direct Dependencies
- `point_of_sale` - Core POS module

### Optional Dependencies
- `pos_restaurant` - For floor screen support

### External Libraries (included via Odoo)
- FontAwesome - For icons
- OWL - Component framework
- Web Dialog - Modal/Dialog system

---

## Troubleshooting Guide

### Issue: "Chrome component not found"
**Solution**: POS module might not be fully loaded. Check module dependencies.

### Issue: Modal shows but styling is broken
**Solution**: CSS file not loaded. Clear browser cache, check network tab.

### Issue: Clicking buttons does nothing
**Solution**: Dialog service might not be available. Check browser console for errors.

### Issue: Modal appears behind other content
**Solution**: Increase `z-index` value in CSS:
```css
.pos-session-type-modal-overlay {
    z-index: 10000;  /* Increase if needed */
}
```

---

## File Change Reference

### When Making Changes

| File | Purpose | Impact |
|------|---------|--------|
| `__manifest__.py` | Module config | Must refresh module list |
| `session_type_selector.js` | Logic | Must clear browser cache |
| `session_type_selector.xml` | Template | Must clear browser cache |
| `session_type_selector.css` | Styling | Clear browser cache for instant changes |

### Cache Clearing

**Development Mode**:
```bash
# Clear Odoo cache
rm -rf ~/.local/share/Odoo/*/filestore

# Or use --dev=all flag
odoo-bin --dev=all
```

**Browser**:
- DevTools → Network → Disable cache
- Or use Ctrl+Shift+Del to clear cache

---

## Migration Notes

If upgrading from previous versions:

1. Backup `__manifest__.py`
2. Update version number in `__manifest__.py`
3. Clear browser cache
4. Update module in Odoo
5. Test all functionality

---

## Best Practices

✅ **DO**:
- Use OWL components properly
- Patch only the methods you need
- Add try-catch blocks around patches
- Store data in sessionStorage for session-scoped data
- Comment complex logic
- Test in multiple browsers

❌ **DON'T**:
- Modify original files without patching
- Use global variables unnecessarily
- Hardcode values (use config)
- Ignore error handling
- Skip testing on different screen sizes
- Forget about mobile optimization

---

## Resources

- [Odoo 17 Documentation](https://www.odoo.com/documentation/17.0/)
- [OWL Framework](https://github.com/odoo/owl)
- [POS Module Source Code](odoo/addons/point_of_sale/)

---

**Last Updated**: 2026-05-02
**Version**: 17.0.1.0.0
