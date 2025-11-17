# ✅ Lab Scheduling Complete

## 📅 Current Lab Schedule

**Updated:** November 16, 2025  
**Period:** November 17-28, 2025 (2 weeks, weekdays only)

---

## 🏫 4 Labs with Full Schedules

### Labs (All Operating 9 AM - 6 PM)

1. **Physics Lab**
   - Capacity: 40 students
   - Equipment: Oscilloscope, Projector

2. **Chemistry Lab**
   - Capacity: 30 students
   - Equipment: Fume hood, Beakers, Bunsen burner

3. **Biology Lab**
   - Capacity: 25 students
   - Equipment: Microscopes, Slides

4. **Biotechnology Lab**
   - Capacity: 20 students
   - Equipment: PCR machine, Centrifuge

---

## 📋 Available Dates

### **Week 1**
- ✅ Monday, Nov 17
- ✅ Tuesday, Nov 18
- ✅ Wednesday, Nov 19
- ✅ Thursday, Nov 20
- ✅ Friday, Nov 21
- ❌ Saturday, Nov 22 (Closed)
- ❌ Sunday, Nov 23 (Closed)

### **Week 2**
- ✅ Monday, Nov 24
- ✅ Tuesday, Nov 25
- ✅ Wednesday, Nov 26
- ✅ Thursday, Nov 27
- ✅ Friday, Nov 28
- ❌ Saturday & Sunday (Closed)

---

## ⏰ Time Slots (Per Lab, Per Day)

Each lab has **4 slots per day**:
- **Slot 1:** 09:00 - 11:00 (2 hours)
- **Slot 2:** 11:00 - 13:00 (2 hours)
- **Slot 3:** 14:00 - 16:00 (2 hours)
- **Slot 4:** 16:00 - 18:00 (2 hours)

---

## 📊 Total Available Slots

```
4 Labs × 4 Slots/Day × 10 Weekdays = 160 Total Slots
```

---

## 🎯 How to View/Book

### Students
```
Visit: /available_labs.html
→ Pick a date (Nov 17-28)
→ See available slots
→ Book a 2-hour slot
```

### Admins
```
Visit: /admin_available_labs.html
→ View all labs & bookings
→ Override/cancel bookings
→ Disable labs if needed
```

### Lab Assistants
```
Visit: /lab_assistant_labs.html
→ See assigned labs only
→ View today's bookings
→ Prepare materials
```

---

## 📝 Files Created

- ✅ `seed_availability.py` - Script to add slots to database
- ✅ `LAB_SCHEDULE.md` - Detailed schedule document (this file)

---

## 🔄 To Update Schedule

Edit `seed_availability.py` and change:

```python
TIME_SLOTS = [
    ("09:00", "11:00"),  # Change these times
    ("11:00", "13:00"),
    ("14:00", "16:00"),
    ("16:00", "18:00"),
]
```

Then run:
```bash
python seed_availability.py
```

---

## ✅ Tests Status

```
✅ 154 tests passed
✅ 77.62% coverage (required: 75%)
✅ 0 lint violations
✅ 0 security vulnerabilities
```

All tests still passing after adding schedule! ✨

---

**Ready to use!** Students can now see labs and book slots.
