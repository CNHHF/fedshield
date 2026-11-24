<template>
  <div class="rule-expression">
    <template v-if="groupKey">
      <div class="rule-expression__head"><el-select :model-value="groupKey" @update:model-value="changeGroup"><el-option label="全部满足（且）" value="all"/><el-option label="任一满足（或）" value="any"/></el-select><el-button text @click="add(false)">＋条件</el-button><el-button text @click="add(true)">＋条件组</el-button></div>
      <div v-for="(child,i) in modelValue[groupKey]" :key="i" class="rule-expression__child"><RuleExpressionEditor :model-value="child" @update:model-value="replace(i,$event)"/><el-button text title="删除此条件" :disabled="modelValue[groupKey].length===1" @click="remove(i)">×</el-button></div>
    </template>
    <div v-else class="rule-expression__leaf">
      <el-select :model-value="modelValue.field" @update:model-value="changeField"><el-option v-for="(name,key) in fields" :key="key" :value="key" :label="name"/></el-select>
      <el-select :model-value="modelValue.op" @update:model-value="set('op',$event)"><el-option v-for="op in operators" :key="op" :value="op" :label="opLabels[op]"/></el-select>
      <el-switch v-if="booleans.includes(modelValue.field)" :model-value="modelValue.value" active-text="是" inactive-text="否" @update:model-value="set('value',$event)"/>
      <el-input-number v-else-if="numbers.includes(modelValue.field)" :model-value="modelValue.value" controls-position="right" @update:model-value="set('value',$event)"/>
      <el-select v-else-if="modelValue.op==='in'" :model-value="modelValue.value" multiple filterable allow-create default-first-option @update:model-value="set('value',$event)"/>
      <el-input v-else :model-value="modelValue.value" @update:model-value="set('value',$event)"/>
    </div>
  </div>
</template>
<script setup>
import {computed} from 'vue'
const props=defineProps({modelValue:{type:Object,required:true}}),emit=defineEmits(['update:modelValue'])
const fields={sourceRegion:'来源地区',targetRegion:'处理目的地',dataLevel:'数据级别',authorized:'已登记授权',hasScc:'已登记传输依据',hasDpia:'已登记影响评估',crossBorder:'跨境处理',customerIdPresent:'含客户编号',amount:'单笔金额',fieldCount:'批次记录数',lineCount:'订单明细数',quantity:'商品件数',currency:'币种',customerCountry:'客户国家',purpose:'用途'}
const booleans=['authorized','hasScc','hasDpia','crossBorder','customerIdPresent'],numbers=['amount','fieldCount','lineCount','quantity']
const opLabels={eq:'等于',ne:'不等于',gt:'大于',gte:'不少于',lt:'小于',lte:'不超过',in:'属于',contains:'包含'}
const groupKey=computed(()=>props.modelValue.all?'all':props.modelValue.any?'any':'')
const operators=computed(()=>booleans.includes(props.modelValue.field)?['eq','ne']:numbers.includes(props.modelValue.field)?['eq','ne','gt','gte','lt','lte']:['eq','ne','in','contains'])
function set(k,v){const value={...props.modelValue,[k]:v};if(k==='op'){if(v==='in'&&!Array.isArray(value.value))value.value=[String(value.value)];if(v!=='in'&&Array.isArray(value.value))value.value=value.value[0]||''}emit('update:modelValue',value)}
function changeField(field){emit('update:modelValue',{field,op:'eq',value:booleans.includes(field)?false:numbers.includes(field)?0:''})}
function changeGroup(key){emit('update:modelValue',{[key]:props.modelValue[groupKey.value]})}
function replace(i,value){const children=[...props.modelValue[groupKey.value]];children[i]=value;emit('update:modelValue',{[groupKey.value]:children})}
function remove(i){emit('update:modelValue',{[groupKey.value]:props.modelValue[groupKey.value].filter((_,j)=>i!==j)})}
function add(group){const leaf={field:'authorized',op:'eq',value:false};emit('update:modelValue',{[groupKey.value]:[...props.modelValue[groupKey.value],group?{all:[leaf]}:leaf]})}
</script>
<style scoped>
.rule-expression{min-width:0;width:100%}.rule-expression__head{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin-bottom:12px}.rule-expression__head>.el-select{width:160px}.rule-expression__child{display:flex;gap:4px;padding:10px 0 10px 10px;border-left:2px solid #e3e9f2;margin:6px 0}.rule-expression__child>.rule-expression{flex:1}.rule-expression__leaf{display:grid;gap:8px}.rule-expression__leaf>*{width:100%}.rule-expression__child>.el-button{flex-shrink:0;padding:4px}
</style>
