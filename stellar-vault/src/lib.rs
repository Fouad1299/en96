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
