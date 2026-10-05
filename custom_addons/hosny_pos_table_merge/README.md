# Hosny POS Table Merge Module

## 🍽️ Professional Restaurant POS Table Merge Feature

A complete, production-grade Odoo 17 module that implements a sophisticated "Merge Tables" feature for Restaurant POS systems.

---

## 📋 Table of Contents

1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Upgrade & Restart](#upgrade--restart)
5. [Usage](#usage)
6. [Technical Architecture](#technical-architecture)
7. [API Documentation](#api-documentation)
8. [Testing Guide](#testing-guide)
9. [Troubleshooting](#troubleshooting)
10. [Support & Contribution](#support--contribution)

---

## ✨ Features

### Core Functionality
- **Multiple Table Merge**: Merge orders from 2+ tables into one destination table
- **Modern UI/UX**: Premium OWL popup with RTL support (Arabic)
- **Non-Destructive**: Preserves all order data during merge
- **Smart Selection**: Checkbox interface for table selection
- **Real-time Summaries**: Shows order totals and item counts before merge

### Data Preservation
- ✅ Order line quantities
- ✅ Unit prices and discounts
- ✅ Tax calculations
- ✅ Product notes and customer comments
- ✅ Combo items and variants
- ✅ Product attributes
- ✅ Kitchen printing flow
- ✅ Payment processing compatibility

### UI/UX Features
- 🎨 Modern premium design matching current POS theme
- 📱 Fully responsive (desktop, tablet, mobile)
- 🌍 Arabic RTL support
- ✨ Smooth animations and transitions
- 🔔 Real-time merge summary
- ⚠️ Confirmation dialogs
- 🎯 Professional spacing and typography

### POS Integration
- 📍 Button placed in existing action buttons section
- 🔄 Multi-session compatible
- 🖨️ Kitchen printing compatible
- 💳 Payment flow integration
- 🔐 No core file modifications

---

## 🔧 Requirements

### Odoo Version
- **Odoo 17** (Enterprise or Community)

### Dependencies
- `point_of_sale` - Base POS module
- `pos_restaurant` - Restaurant-specific POS features

### System Requirements
- Python 3.8+
- Modern browser with ES6+ support
- 100MB disk space

---

## 📦 Installation

### Step 1: Download/Copy Module

Clone or download the module to your Odoo custom addons directory:

```bash
# Navigate to custom addons
cd /opt/odoo17-source/custom_addons

# Module should be at:
/opt/odoo17-source/custom_addons/hosny_pos_table_merge/
```

### Step 2: Verify Module Structure

Ensure the following structure exists:

```
hosny_pos_table_merge/
├── __init__.py
├── __manifest__.py
├── models/
│   └── __init__.py
├── static/
│   └── src/
│       ├── js/
│       │   ├── pos_table_merge.js
│       │   ├── merge_popup.js
│       │   └── merge_handler.js
│       ├── xml/
│       │   └── merge_popup.xml
│       └── scss/
│           └── merge_popup.scss
├── views/
│   └── assets.xml
└── README.md
```

### Step 3: Install Module via Odoo UI

1. Open Odoo in a browser
2. Go to **Apps** → Search for **"Hosny POS Table Merge"**
3. Click **Install**

Alternatively, via command line (see next section).

---

## 🚀 Upgrade & Restart

### Option 1: Command Line Installation

```bash
# Navigate to Odoo directory
cd /opt/odoo17-source

# Install via command
python odoo-bin -c /path/to/odoo.conf -d database_name -i hosny_pos_table_merge --stop-after-init

# Example for local setup
python odoo-bin -c etc/odoo.conf -d odoo17_prod -i hosny_pos_table_merge --stop-after-init
```

### Option 2: Via Odoo Shell

```bash
# Enter Odoo shell
python odoo-bin shell -d odoo17_prod

# Install module
>>> env['ir.module.module'].search([('name', '=', 'hosny_pos_table_merge')]).button_immediate_install()
>>> exit()
```

### Step 4: Upgrade Odoo Database

```bash
# After installation, upgrade database
cd /opt/odoo17-source

# Method 1: Using command line
python odoo-bin -c etc/odoo.conf -d odoo17_prod -u all

# Method 2: Using web interface
# Go to Settings → Users & Companies → Activate Developer Mode
# Then go to Apps → Update Apps List → Update
```

### Step 5: Restart Odoo Service

```bash
# Stop Odoo service
sudo systemctl stop odoo

# Clear cache (optional but recommended)
sudo rm -rf /tmp/odoo_*
sudo rm -rf ~/.local/share/Odoo/sessions/*

# Start Odoo service
sudo systemctl start odoo

# Verify service is running
sudo systemctl status odoo

# Check logs
sudo journalctl -u odoo -f
```

### Step 6: Clear Browser Cache

After restart, clear your browser cache:

```bash
# For Chrome/Chromium: Ctrl+Shift+Delete
# For Firefox: Ctrl+Shift+Delete
# For Safari: Cmd+Shift+Delete
```

Or manually reload POS with cache clear:

```javascript
// Open browser console (F12) in POS
window.location.reload(true);  // Hard refresh
```

---

## 📖 Usage

### Opening the Merge Feature

1. Open POS application
2. Start a restaurant order and open a table
3. Look for **"دمج الطاولات"** (Merge Tables) button in the action buttons section
4. Button is located next to the **"تحويل"** (Transfer) button

### Merge Workflow

#### Step 1: Select Tables
- Click the **Merge Tables** button
- Modern popup opens showing:
  - Current table (destination) at top
  - All other occupied tables below
  - Each table shows: name, item count, total amount

#### Step 2: Select Source Tables
- Click checkbox on each table you want to merge
- Selected tables highlight in green
- Merge summary updates in real-time

#### Step 3: Review Merge Summary
- See total tables selected
- Total items being merged
- Total amount from selected tables

#### Step 4: Confirm Merge
- Click **"تأكيد الدمج"** (Confirm Merge) button
- System merges all selected tables into current table
- Source tables become empty

#### Step 5: Complete Order
- All merged items now appear in current table
- Process payment normally
- Kitchen gets all print jobs

---

## 🏗️ Technical Architecture

### Module Structure

```
hosny_pos_table_merge/
│
├── Python Layer (Minimal)
│   ├── __init__.py          - Package initialization
│   ├── __manifest__.py      - Module metadata & dependencies
│   └── models/__init__.py   - Model definitions (currently empty)
│
├── Frontend Layer (OWL)
│   ├── static/src/js/
│   │   ├── pos_table_merge.js    - Module initialization & patching
│   │   ├── merge_popup.js        - OWL popup component class
│   │   └── merge_handler.js      - Core merge business logic
│   │
│   ├── static/src/xml/
│   │   └── merge_popup.xml       - OWL template
│   │
│   └── static/src/scss/
│       └── merge_popup.scss      - Styling (SCSS with RTL support)
│
├── Views Layer
│   └── views/assets.xml          - Asset registration
│
└── Documentation
    └── README.md                 - This file
```

### Component Flow

```
POS Start
    ↓
Load pos_table_merge.js (Module Init)
    ↓
Patch ActionpadWidget
    ↓
Add "Merge Tables" Button
    ↓
User Clicks Button
    ↓
Initialize Popup Component (merge_popup.js)
    ↓
Fetch Available Tables
    ↓
Render Table Selection UI
    ↓
User Selects Tables & Confirms
    ↓
Call merge_handler.js (Business Logic)
    ↓
Clone Order Lines
    ↓
Update Tables
    ↓
Close Source Tables
    ↓
Success Notification
```

### Key Classes

#### `MergeTablesPopup` (merge_popup.js)
- OWL component for popup UI
- Methods:
  - `toggleTableSelection()` - Select/deselect tables
  - `getSelectedAmount()` - Calculate total amount
  - `confirmMerge()` - Validate and trigger merge
  - `formatCurrency()` - Format prices

#### `TableMergeHandler` (merge_handler.js)
- Core merge business logic
- Methods:
  - `mergeTables()` - Main merge orchestration
  - `mergeOrderLines()` - Combine lines from source → destination
  - `cloneOrderLine()` - Preserve all order line data
  - `validateMerge()` - Pre-merge validation
  - `getMergeSummary()` - Generate merge report

---

## 🔌 API Documentation

### Main Merge Function

```javascript
/**
 * Merge multiple tables into current table
 * 
 * @param {PosStore} posStore - POS data store
 * @param {Table} currentTable - Destination table
 * @param {Array} selectedTableIds - Source table IDs
 * @returns {Promise<Object>} Merge result
 * 
 * @example
 * const result = await TableMergeHandler.mergeTables(
 *   posStore,
 *   currentTable,
 *   [tableId1, tableId2]
 * );
 */
async mergeTables(posStore, currentTable, selectedTableIds)
```

### Validation Function

```javascript
/**
 * Validate merge operation before execution
 * 
 * @param {Table} currentTable - Destination table
 * @param {Array} selectedTableIds - Source table IDs
 * @returns {Object} { valid: boolean, errors: Array }
 * 
 * @example
 * const validation = TableMergeHandler.validateMerge(
 *   currentTable,
 *   selectedTableIds
 * );
 */
validateMerge(currentTable, selectedTableIds)
```

### Summary Function

```javascript
/**
 * Generate merge operation summary
 * 
 * @param {Table} currentTable - Destination table
 * @param {Array} selectedTables - Source tables
 * @returns {Object} Summary with counts and amounts
 * 
 * @example
 * const summary = TableMergeHandler.getMergeSummary(
 *   currentTable,
 *   selectedTables
 * );
 */
getMergeSummary(currentTable, selectedTables)
```

---

## 🧪 Testing Guide

### Manual Testing Checklist

#### Pre-Merge Setup
- [ ] Create 3+ restaurant tables
- [ ] Add items to each table
- [ ] Verify POS displays all tables

#### Merge Interface
- [ ] Click "Merge Tables" button appears
- [ ] Popup opens with correct styling
- [ ] Current table shown at top
- [ ] All available tables listed below
- [ ] Table information displays correctly (items, amounts)

#### Table Selection
- [ ] Click checkbox to select table
- [ ] Selected table highlights in green
- [ ] Uncheck to deselect
- [ ] Summary updates in real-time
- [ ] Can select multiple tables

#### Merge Operation
- [ ] Click "Confirm Merge"
- [ ] Merge completes without errors
- [ ] Current table has all items
- [ ] Source tables are empty
- [ ] No data corruption

#### Order Integrity
- [ ] Product names preserved
- [ ] Quantities correct
- [ ] Prices unchanged
- [ ] Discounts preserved
- [ ] Taxes calculated correctly
- [ ] Notes/comments intact

#### Payment Processing
- [ ] Can process payment after merge
- [ ] Receipt shows all items
- [ ] No payment errors
- [ ] Kitchen printing works

#### Edge Cases
- [ ] Merge single table (should work)
- [ ] Merge tables with combos
- [ ] Merge with variants
- [ ] Merge with discounts
- [ ] Merge with notes
- [ ] Large order merge (50+ items)

### Automated Testing (Jest)

Create test file: `static/src/js/__tests__/merge_handler.test.js`

```javascript
import { TableMergeHandler } from '../merge_handler.js';

describe('TableMergeHandler', () => {
    
    describe('validateMerge', () => {
        test('should reject no current table', () => {
            const result = TableMergeHandler.validateMerge(null, [1, 2]);
            expect(result.valid).toBe(false);
        });

        test('should reject no selected tables', () => {
            const table = { id: 1, name: 'Table 1' };
            const result = TableMergeHandler.validateMerge(table, []);
            expect(result.valid).toBe(false);
        });

        test('should accept valid merge', () => {
            const table = { id: 1, name: 'Table 1' };
            const result = TableMergeHandler.validateMerge(table, [2, 3]);
            expect(result.valid).toBe(true);
        });
    });

    describe('getMergeSummary', () => {
        test('should calculate correct summary', () => {
            // Your test implementation
        });
    });

    describe('mergeTables', () => {
        test('should merge orders without data loss', async () => {
            // Your test implementation
        });
    });
});
```

### Database Testing

```bash
# Test in PostgreSQL
psql -d odoo17_prod -U odoo

# Check table records
SELECT id, name FROM restaurant_table ORDER BY id;

# Check orders
SELECT id, table_id FROM pos_order ORDER BY id;

# Check order lines
SELECT id, order_id, product_id, qty FROM pos_order_line ORDER BY id;
```

---

## 🐛 Troubleshooting

### Issue: Button Not Appearing

**Symptoms**: "Merge Tables" button not visible in POS

**Solutions**:
1. Clear browser cache (Ctrl+Shift+Delete)
2. Hard refresh POS page (Ctrl+Shift+R)
3. Clear Odoo cache:
   ```bash
   rm -rf ~/.local/share/Odoo/*
   ```
4. Restart Odoo service:
   ```bash
   sudo systemctl restart odoo
   ```
5. Check module is installed:
   ```bash
   python odoo-bin shell -d database_name
   >>> env['ir.module.module'].search([('name', '=', 'hosny_pos_table_merge')])
   >>> exit()
   ```

### Issue: Popup Not Opening

**Symptoms**: Click button but nothing happens

**Solutions**:
1. Check browser console for errors (F12 → Console)
2. Check Odoo logs:
   ```bash
   sudo journalctl -u odoo -f
   ```
3. Verify JavaScript files are loaded:
   - F12 → Network tab
   - Refresh page
   - Look for merge_popup.js, merge_handler.js
4. Check XML template:
   ```bash
   grep -r "MergeTablesPopup" /opt/odoo17-source/custom_addons/hosny_pos_table_merge/
   ```

### Issue: Merge Doesn't Work

**Symptoms**: Click confirm but merge fails

**Solutions**:
1. Check browser console errors (F12 → Console)
2. Verify tables have orders:
   ```sql
   SELECT t.id, t.name, COUNT(o.id) as orders
   FROM restaurant_table t
   LEFT JOIN pos_order o ON o.table_id = t.id
   GROUP BY t.id;
   ```
3. Check order lines exist:
   ```sql
   SELECT order_id, COUNT(*) as lines FROM pos_order_line GROUP BY order_id;
   ```

### Issue: Data Corruption After Merge

**Symptoms**: Prices/quantities wrong after merge

**Solutions**:
1. Check merge_handler.js cloneOrderLine() function
2. Verify all fields are copied:
   - quantity, price_unit, discount, tax_ids
   - note, full_product_name, customerNote
   - combo, combo_parent_id, combo_line_ids
3. Test with small items first (1-2 items)

### Issue: Style Issues

**Symptoms**: Popup looks wrong or misaligned

**Solutions**:
1. Check SCSS compilation:
   ```bash
   ls -la /opt/odoo17-source/custom_addons/hosny_pos_table_merge/static/src/scss/
   ```
2. Verify CSS is loaded:
   - F12 → Network tab
   - Search for "merge_popup.scss"
3. Check RTL is applied:
   - Inspect element
   - Look for `dir="rtl"` attribute
4. Clear theme cache:
   ```bash
   rm -rf ~/.local/share/Odoo/themes/*
   ```

### Issue: Performance Issues

**Symptoms**: Merge slow with many tables/items

**Solutions**:
1. Reduce number of tables (test with 3-5 first)
2. Check for JavaScript errors in console
3. Monitor browser performance (F12 → Performance)
4. Check Odoo CPU/memory usage:
   ```bash
   top -p $(pgrep -f odoo-bin | tr '\n' ',')
   ```

### Issue: Multi-Session Issues

**Symptoms**: Merge fails in multi-session setup

**Solutions**:
1. Ensure POS syncs before merge
2. Check sessions table:
   ```sql
   SELECT id, name, state FROM pos_session;
   ```
3. Clear old sessions:
   ```bash
   python odoo-bin shell -d database_name
   >>> env['pos.session'].search([('state', '!=', 'open')]).unlink()
   ```

---

## 📞 Support & Contribution

### Getting Help

1. **Check Logs**:
   ```bash
   tail -f /var/log/odoo/odoo.log
   ```

2. **Enable Debug Mode**:
   ```bash
   python odoo-bin -d database_name --debug
   ```

3. **Browser Dev Tools**:
   - Press F12 in browser
   - Check Console tab for errors
   - Check Network tab for failed requests

### Reporting Issues

Include:
- Odoo version (Settings → About)
- Module version (from __manifest__.py)
- Error message (browser console + odoo logs)
- Steps to reproduce
- Screenshot if UI issue

### Contributing

1. Fork the module
2. Create feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -am 'Add feature'`
4. Push branch: `git push origin feature/my-feature`
5. Create Pull Request

---

## 📄 License

This module is licensed under LGPL-3 (GNU Lesser General Public License v3.0).

See LICENSE file for details.

---

## 🎉 Credits

**Developer**: Hosny Development Team  
**Odoo Version**: 17.0  
**Release Date**: 2024  
**Last Updated**: 2024

---

## 📊 Version History

### v17.0.1.0.0 (Initial Release)
- ✨ Complete table merge functionality
- 🎨 Modern OWL popup interface
- 🌍 Arabic RTL support
- 🔄 Multi-session compatibility
- 📱 Responsive design
- 🍽️ Restaurant POS integration

---

## 🎯 Roadmap

Future enhancements:
- [ ] Bulk merge shortcuts (merge all occupied tables)
- [ ] Merge history audit log
- [ ] Partial merge (select specific items)
- [ ] Merge templates (save merge configurations)
- [ ] Performance optimizations
- [ ] Extended reporting
- [ ] Mobile app integration

---

**Happy Merging! 🍽️✨**

For support, contact: support@hosny-dev.com
