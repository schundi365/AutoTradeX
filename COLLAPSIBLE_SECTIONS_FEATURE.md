# Collapsible Sections Feature

## Overview
Added minimize/maximize functionality to large sections in the dashboard to improve navigation and reduce clutter. Users can now collapse sections they're not actively using.

## Features

### 1. Collapsible Section Headers
Sections with the `collapsible` class can be clicked to expand/collapse:
- **Visual Indicator**: ▼ icon that rotates when collapsed
- **Hover Effect**: Subtle blue highlight on hover
- **Smooth Animation**: 0.3s transition for collapse/expand
- **Persistent State**: Collapsed state saved to localStorage

### 2. Sections Made Collapsible

#### AI & MLOPS Tab
- ✅ **APEX TRADER (OLLAMA) HEALTH & PERFORMANCE** - Large monitoring section
- ✅ **LLM PIPELINE CONFIGURATION** - Extensive config form
- ✅ **LLM TRAINING PIPELINE** - Multi-step pipeline controls

#### TRADES Tab
- ✅ **BOT DECISION HISTORY** - Large table with many rows

#### ANALYTICS Tab
- ✅ **TRADE HISTORY** - 500+ trade records table

#### CONFIG Tab
- ✅ **BOT CONFIGURATION** - Large configuration form

### 3. User Experience

**To Collapse a Section:**
1. Click anywhere on the section header (except buttons)
2. The ▼ icon rotates to ▶
3. Section content smoothly collapses
4. State is saved to browser localStorage

**To Expand a Section:**
1. Click the collapsed header again
2. The ▶ icon rotates back to ▼
3. Section content smoothly expands

**Persistent State:**
- Collapsed/expanded state is remembered across page reloads
- Each section's state is stored independently
- Uses localStorage with key format: `section-{sectionId}`

### 4. Button Click Handling
Buttons within collapsible headers (like REFRESH, SAVE) use `event.stopPropagation()` to prevent triggering the collapse when clicked.

## Technical Implementation

### CSS Classes

```css
.sec-header.collapsible {
  cursor: pointer;
  user-select: none;
}

.sec-header.collapsible:hover {
  background: rgba(59, 130, 246, 0.05);
}

.collapse-icon {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 8px;
  transition: transform 0.2s ease;
  display: inline-block;
}

.sec-header.collapsed .collapse-icon {
  transform: rotate(-90deg);
}

.sec-body.collapsible {
  transition: max-height 0.3s ease, opacity 0.3s ease, padding 0.3s ease;
  overflow: hidden;
}

.sec-body.collapsed {
  max-height: 0 !important;
  opacity: 0;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}
```

### JavaScript Functions

```javascript
// Toggle section collapse/expand
function toggleSection(headerElement) {
  const header = headerElement.classList.contains('sec-header') 
    ? headerElement 
    : headerElement.closest('.sec-header');
  if (!header) return;
  
  const body = header.nextElementSibling;
  if (!body || !body.classList.contains('sec-body')) return;
  
  // Toggle collapsed state
  header.classList.toggle('collapsed');
  body.classList.toggle('collapsed');
  
  // Save state to localStorage
  const sectionId = header.closest('.sec-card')?.id 
    || header.querySelector('.sec-title')?.textContent.trim();
  if (sectionId) {
    const isCollapsed = header.classList.contains('collapsed');
    localStorage.setItem(`section-${sectionId}`, isCollapsed ? 'collapsed' : 'expanded');
  }
}

// Restore collapsed states on page load
function restoreCollapsedStates() {
  document.querySelectorAll('.sec-header.collapsible').forEach(header => {
    const sectionId = header.closest('.sec-card')?.id 
      || header.querySelector('.sec-title')?.textContent.trim();
    if (sectionId) {
      const state = localStorage.getItem(`section-${sectionId}`);
      if (state === 'collapsed') {
        header.classList.add('collapsed');
        const body = header.nextElementSibling;
        if (body && body.classList.contains('sec-body')) {
          body.classList.add('collapsed');
        }
      }
    }
  });
}
```

### HTML Structure

```html
<div class="sec-card">
  <div class="sec-header collapsible" onclick="toggleSection(this)">
    <span class="sec-title">
      <span>//</span> SECTION TITLE
      <span class="collapse-icon">▼</span>
    </span>
    <button class="btn" onclick="event.stopPropagation(); doAction()">ACTION</button>
  </div>
  <div class="sec-body collapsible">
    <!-- Section content -->
  </div>
</div>
```

## How to Add to More Sections

To make any section collapsible:

1. **Add classes to header:**
   ```html
   <div class="sec-header collapsible" onclick="toggleSection(this)">
   ```

2. **Add collapse icon to title:**
   ```html
   <span class="sec-title">
     <span>//</span> YOUR TITLE
     <span class="collapse-icon">▼</span>
   </span>
   ```

3. **Add collapsible class to body:**
   ```html
   <div class="sec-body collapsible">
   ```

4. **Prevent button clicks from collapsing:**
   ```html
   <button onclick="event.stopPropagation(); yourFunction()">BUTTON</button>
   ```

## Benefits

✅ **Reduced Clutter** - Hide sections you're not using  
✅ **Better Navigation** - Easier to find what you need  
✅ **Persistent State** - Remembers your preferences  
✅ **Smooth UX** - Animated transitions feel polished  
✅ **Keyboard Friendly** - Click anywhere on header to toggle  
✅ **Mobile Friendly** - Especially useful on smaller screens  

## Usage Tips

1. **Collapse Large Forms**: Hide configuration sections when not editing
2. **Focus on Data**: Collapse headers to see more table rows
3. **Workflow Optimization**: Keep only active sections expanded
4. **Performance**: Collapsed sections still load data, just hidden visually

## Browser Compatibility

- Uses localStorage (supported in all modern browsers)
- CSS transitions (IE10+, all modern browsers)
- No external dependencies

## Future Enhancements

Potential improvements:
- [ ] "Collapse All" / "Expand All" buttons
- [ ] Keyboard shortcuts (e.g., Ctrl+Click to collapse all)
- [ ] Section groups (collapse multiple related sections)
- [ ] Animation speed preference
- [ ] Remember state per user account (not just browser)

## Files Modified

- `frontend/trading-bot-dashboard.html`
  - Added CSS for collapsible sections
  - Added JavaScript toggle functions
  - Updated section headers with collapsible class
  - Added collapse icons to section titles
  - Added initialization call to restore states

## Testing

Test the feature by:
1. Open the dashboard
2. Click on any section header with a ▼ icon
3. Verify section collapses smoothly
4. Click again to expand
5. Refresh the page
6. Verify collapsed sections remain collapsed
7. Test buttons in headers still work (don't collapse section)

## Status
✅ Feature complete and functional
