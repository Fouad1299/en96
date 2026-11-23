#![no_std]

use soroban_sdk::{
    contract, contractimpl, contracttype,
    Address, Env, String,
};

#[contracttype]
#[derive(Clone)]
pub enum DataKey {
    Admin,
    Token,
    Initialized,
    Paused,
}

#[contract]
pub struct EN96StellarVault;

#[contractimpl]
impl EN96StellarVault {
    pub fn initialize(
        env: Env,
        admin: Address,
        token: Address,
    ) {
        if env.storage().instance().has(&DataKey::Initialized) {
            panic!("Already initialized");
        }

        admin.require_auth();

        env.storage().instance().set(&DataKey::Admin, &admin);
        env.storage().instance().set(&DataKey::Token, &token);
        env.storage().instance().set(&DataKey::Paused, &true);
        env.storage().instance().set(&DataKey::Initialized, &true);
    }

    pub fn is_paused(env: Env) -> bool {
        env.storage()
            .instance()
            .get(&DataKey::Paused)
            .unwrap_or(true)
    }

    pub fn token(env: Env) -> Address {
        env.storage()
            .instance()
            .get(&DataKey::Token)
            .expect("Not initialized")
    }

    pub fn reserve_balance(env: Env) -> i128 {
        let token: Address = env.storage()
            .instance()
            .get(&DataKey::Token)
            .expect("Not initialized");

        let client = soroban_sdk::token::Client::new(&env, &token);
        client.balance(&env.current_contract_address())
    }

    pub fn status(env: Env) -> String {
        String::from_str(
            &env,
            "DESIGN ONLY - NO WITHDRAWALS OR MINTING",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use soroban_sdk::testutils::Address as _;
    use soroban_sdk::token::{
        StellarAssetClient, Client as TokenClient,
    };

    fn setup() -> (
        Env,
        EN96StellarVaultClient<'static>,
        Address,
        Address,
    ) {
        // Tests create isolated environments.
        // No real network transactions occur.
        let env = Env::default();
        env.mock_all_auths();

        let admin = Address::generate(&env);
        let token_admin = Address::generate(&env);

        let token = env
            .register_stellar_asset_contract_v2(token_admin)
            .address();

        let contract_id = env.register(EN96StellarVault, ());
        let client = EN96StellarVaultClient::new(
            &env,
            &contract_id,
        );

        client.initialize(&admin, &token);

        // Return addresses only; construct clients as needed.
        (env, client, admin, token)
    }

    #[test]
    fn starts_paused_and_keeps_token_address() {
        let (_env, client, _admin, token) = setup();

        assert!(client.is_paused());
        assert_eq!(client.token(), token);
    }

    #[test]
    fn cannot_initialize_twice() {
        let (env, client, admin, token) = setup();

        let result = client.try_initialize(&admin, &token);

        assert!(result.is_err());

        // The original initialization remains unchanged.
        assert!(client.is_paused());
        assert_eq!(client.token(), token);

        let _ = env;
    }

    #[test]
    fn reports_zero_reserve_before_deposit() {
        let (_env, client, _admin, _token) = setup();

        assert_eq!(client.reserve_balance(), 0);
    }

    #[test]
    fn reports_tokens_received_without_withdrawing() {
        let (env, client, _admin, token) = setup();

        let receiver = client.address.clone();
        let amount: i128 = 1_000_000_000;

        let asset_admin = StellarAssetClient::new(&env, &token);
        asset_admin.mint(&receiver, &amount);

        let token_client = TokenClient::new(&env, &token);

        assert_eq!(
            token_client.balance(&receiver),
            amount,
        );
        assert_eq!(client.reserve_balance(), amount);
        assert!(client.is_paused());
    }

    #[test]
    fn reports_design_only_status() {
        let (env, client, _admin, _token) = setup();

        assert_eq!(
            client.status(),
            String::from_str(
                &env,
                "DESIGN ONLY - NO WITHDRAWALS OR MINTING",
            ),
        );
    }
}
