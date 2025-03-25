#pragma once
#include <sysio/chain/types.hpp>
#include <fc/uint128.hpp>
#include <chainbase/chainbase.hpp>
#include <sysio/chain/block_header.hpp>

#include <boost/multi_index/hashed_index.hpp>
#include <boost/multi_index/global_fun.hpp>

#include <sysio/chain/multi_index_includes.hpp>

namespace sysio {
   using boost::multi_index_container;
   using namespace boost::multi_index;
   using namespace chain;

   /**
    * The purpose of this object is to store the most recent sroot
    */
   class contract_s_root_object : public chainbase::object<contract_s_root_object_type, contract_s_root_object>
   {
         OBJECT_CTOR(contract_s_root_object)

         id_type                id;
         account_name           contract;
         block_id_type          block_id;
         checksum256_type       s_id;
         checksum256_type       s_root;

   };

   inline uint32_t block_num(const contract_s_root_object& contract_s_root) {
      return block_header::num_from_id(contract_s_root.block_id) + 1;;
   }

   namespace s_root_search {
      struct by_id;
      struct by_contract;
      struct by_block_num;
   }

   using contract_s_root_multi_index = chainbase::shared_multi_index_container<
      contract_s_root_object,
      indexed_by<
         ordered_unique< tag<s_root_search::by_id>, member<contract_s_root_object, contract_s_root_object::id_type, &contract_s_root_object::id>>,
         ordered_unique< tag<s_root_search::by_contract>, member< contract_s_root_object, account_name, &contract_s_root_object::contract>>,
         ordered_unique< tag<s_root_search::by_block_num>,
            composite_key< contract_s_root_object,
               global_fun< const contract_s_root_object&, uint32_t, &block_num> ,
               member< contract_s_root_object, contract_s_root_object::id_type, &contract_s_root_object::id>
            >
         >
      >
   >;
} // sysio

CHAINBASE_SET_INDEX_TYPE(sysio::contract_s_root_object, sysio::contract_s_root_multi_index)

FC_REFLECT(sysio::contract_s_root_object, (contract)(block_id)(s_id)(s_root))
