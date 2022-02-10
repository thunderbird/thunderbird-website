import braintree
import flask
import settings
from flask_cors import CORS

app = flask.Flask(__name__)
CORS(app)

gateway = braintree.BraintreeGateway(
    braintree.Configuration(
        braintree.Environment.Sandbox,
        merchant_id=settings.merchant_id,
        public_key=settings.public_key,
        private_key=settings.private_key
    )
)


@app.route("/client_token", methods=["GET"])
def client_token():
    return gateway.client_token.generate()


@app.route("/checkout", methods=["POST"])
def create_donation():
    result = gateway.transaction.sale({
        "amount": flask.request.form['amount'],
        "payment_method_nonce": flask.request.form['payment_method_nonce'],
        "options": {
          "submit_for_settlement": True
        }
    })
    return {"success": result.is_success, "message": result.transaction.status}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
