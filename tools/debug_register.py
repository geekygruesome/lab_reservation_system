from app import app

with app.test_client() as c:
    resp = c.post('/api/register', json={'college_id':'PES1UG23CS456','name':'Test User','email':'test.user@pesu.edu','password':'StrongPass1!','role':'student'})
    print('status', resp.status_code)
    try:
        print('json', resp.get_json())
    except Exception as e:
        print('get_json error', e)
