import os
import pandas as pd
from flask import Flask, render_template, request, redirect, flash, url_for
from flask_socketio import SocketIO, emit
import qrcode
import base64
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'your_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")  # Added CORS support

# Path to the Excel files
EXCEL_FILE = 'items.xlsx'
TXN_FILE = 'transaction_history.xlsx'

# Load or create the Excel files
if not os.path.exists(EXCEL_FILE):
    df = pd.DataFrame(columns=['id', 'name', 'cost'])
    df.to_excel(EXCEL_FILE, index=False)
else:
    df = pd.read_excel(EXCEL_FILE)

if not os.path.exists(TXN_FILE):
    txn_df = pd.DataFrame(columns=['customer_name', 'plot_number', 'items', 'quantities', 'total_cost'])
    txn_df.to_excel(TXN_FILE, index=False)

def save_items_to_excel(dataframe):
    dataframe.to_excel(EXCEL_FILE, index=False)

def save_transaction_to_excel(customer_name, plot_number, items, quantities, total_cost):
    txn_df = pd.read_excel(TXN_FILE)

    # Create a string for the items and their quantities
    items_string = ', '.join([f"{item['name']} (₹{item['cost']}) x{quantity}" for item, quantity in zip(items, quantities)])

    # Create a DataFrame for the new transaction
    new_txn = pd.DataFrame([{
        'customer_name': customer_name,
        'plot_number': plot_number,
        'items': items_string,
        'quantities': ', '.join(map(str, quantities)),
        'total_cost': total_cost
    }])

    # Append the new transaction to the existing transactions
    txn_df = pd.concat([txn_df, new_txn], ignore_index=True)

    # Save to the transaction history Excel file
    txn_df.to_excel(TXN_FILE, index=False)

@app.route('/')
def index():
    # Load items from the Excel file
    df = pd.read_excel(EXCEL_FILE)
    items = df.to_dict(orient='records')
    return render_template('index.html', items=items)

@app.route('/add_item', methods=['POST'])
def add_item():
    name = request.form['name']
    cost = request.form['cost']

    # Load items from the Excel file
    df = pd.read_excel(EXCEL_FILE)

    # Create a new DataFrame with the new item
    new_item = pd.DataFrame([{'id': len(df) + 1, 'name': name, 'cost': cost}])

    # Concatenate the new item to the existing DataFrame
    df = pd.concat([df, new_item], ignore_index=True)

    # Save to Excel file
    save_items_to_excel(df)

    flash('Item added successfully', 'success')
    return redirect(url_for('index'))

@app.route('/remove_item', methods=['POST'])
def remove_item():
    item_id = int(request.form['item_id'])

    # Load items from the Excel file
    df = pd.read_excel(EXCEL_FILE)

    # Remove the item
    df = df[df['id'] != item_id]

    # Save to Excel file
    save_items_to_excel(df)

    flash('Item removed successfully', 'success')
    return redirect(url_for('index'))

@app.route('/place_order', methods=['POST'])
def place_order():
    customer_name = request.form['customer_name']
    plot_number = request.form['plot_number']
    selected_items = request.form.getlist('items[]')
    quantities = request.form.getlist('quantities[]')

    # Load items from the Excel file
    df = pd.read_excel(EXCEL_FILE)

    # Get selected items data and calculate total cost based on quantity
    selected_items_data = df[df['id'].isin([int(i) for i in selected_items])]
    quantities = [int(q) for q in quantities]
    total_cost = sum([item['cost'] * quantity for item, quantity in zip(selected_items_data.to_dict(orient='records'), quantities)])

    # Generate QR code for payment
    qr_data = f'upi://pay?pa=upadhyay.priyanka1-1@okaxis&pn=Priyanka Upadhyay&am={total_cost}&cu=INR'
    qr_img = qrcode.make(qr_data)
    buffer = BytesIO()
    qr_img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    # Zip items and quantities to pass to the template
    zipped_items = zip(selected_items_data.values.tolist(), quantities)

    # Emit the order summary and QR code to connected devices (mobile)
    socketio.emit('order_summary', {
        'customer_name': customer_name,
        'plot_number': plot_number,
        'items': selected_items_data.to_dict(orient='records'),
        'quantities': quantities,
        'total_cost': total_cost,
        'qr_code': qr_base64
    })

    # Save transaction to the transaction history Excel file
    save_transaction_to_excel(customer_name, plot_number, selected_items_data.to_dict(orient='records'), quantities, total_cost)

    # Render the order summary template
    return render_template('order_summary.html', customer_name=customer_name, plot_number=plot_number, total_cost=total_cost, zipped_items=zipped_items, qr_base64=qr_base64)

@app.route('/next_order')
def next_order():
    # Emit a reset signal to clear the mobile view
    socketio.emit('reset_order')
    return redirect(url_for('index'))

@app.route('/mobile')
def mobile_view():
    return render_template('mobile.html')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
